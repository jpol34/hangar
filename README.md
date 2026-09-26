# hangar

Shared RunPod pod-lifecycle library: create, resume, status-check, and stop GPU pods through
RunPod's GraphQL (start/stop/status of an existing pod) and REST v2 (create/update/delete) APIs.

A stopped pod is pinned to the host it last ran on, and that host sometimes has no free GPU
capacity for a resume. `start_pod` handles that transparently: it tries to resume the existing
pod and, on a capacity failure, terminates it and creates a fresh one on a different host.

Originally extracted from near-identical pod-lifecycle code in two sibling projects; this repo is
the single source of truth for that logic going forward.

## Usage

```python
from hangar import PodSpec, init, start_pod

init(api_key)  # call once before any other hangar function

pod_id = start_pod(
    PodSpec(
        name="my-service",
        image="ghcr.io/example/my-service:latest",
        gpu_type_id="NVIDIA GeForce RTX 4090",
        disk_gb=20,
        ports=["8000/http"],
        device_env_key="MY_SERVICE_DEVICE",
        device_env_value="cuda",
        pod_id=existing_pod_id,  # None to always create fresh
        extra_env={"GATEWAY_API_KEY": gateway_api_key},
    )
)
```

`hangar.runpod_client` also exposes the lower-level `create_pod`, `get_pod`, `resume_pod`,
`stop_pod`, `pod_status`, `pod_action`, `delete_pod`, `update_pod_env`, and `PodCapacityError`
directly.

### Network volumes

A pod that needs a durable volume sets `PodSpec.data_center_id`, `network_volume_id`, and
`network_volume_mount_path` — a volume-attached pod must land in its volume's own data center, so
`data_center_id` is required whenever a volume is attached. `ensure_network_volume` mirrors
`start_pod`'s resume-or-create shape: it reuses `volume_id` if it still resolves, otherwise
creates a fresh volume.

```python
from hangar import PodSpec, ensure_network_volume, start_pod

volume_id = ensure_network_volume(
    name="my-service-data",
    size_gb=10,
    data_center_id="US-WA-1",
    volume_id=existing_volume_id,  # None to always create fresh
)

pod_id = start_pod(
    PodSpec(
        ...,
        data_center_id="US-WA-1",
        network_volume_id=volume_id,
        network_volume_mount_path="/runpod-volume",
    )
)
```

This is minimal, single-volume support — no resize, list, or snapshot operations. A network
volume is never auto-deleted; use `hangar.delete_network_volume` when one is no longer needed.

## Idle shutdown

hangar itself only provides the building blocks for detecting whether a pod is idle — deciding
what to do about it (stopping the pod, etc.) is left to each project's own watchdog script. For a
dumb, activity-independent runtime ceiling instead, see **Max-runtime watchdog** below.

### Heartbeat file convention

Activity is recorded by touching the mtime of a single shared file, `/tmp/hangar-heartbeat` by
default (override with the `HANGAR_HEARTBEAT_FILE` env var). Two strategies write to it, and both
can be used together:

- **`hangar-run <command...>`** runs `<command>` as a subprocess, touching the heartbeat once
  immediately and then every `HANGAR_HEARTBEAT_INTERVAL_S` seconds (default 30) for as long as the
  subprocess is alive. It exits with the subprocess's own exit code. This requires zero code
  changes in whatever it wraps — useful for anything that isn't an HTTP server.
- **`hangar.HeartbeatMiddleware`** is a dependency-free ASGI middleware that touches the heartbeat
  on real inbound HTTP requests:

  ```python
  from hangar import HeartbeatMiddleware

  app = HeartbeatMiddleware(app, interval_s=30.0, exclude_paths=["/healthz"])
  ```

  It passes `lifespan` and `websocket` scopes through untouched, and rate-limits writes with a
  cheap `stat()` freshness check rather than touching the file on every request.

`touch_heartbeat()` is a single atomic `os.utime()` call, since the file is written concurrently
by a background thread, an async event loop, and read concurrently by a separate watchdog process.

### Idle detection

`hangar.is_idle(threshold_s)` combines heartbeat freshness with SSH/tty activity via OR: a pod
counts as idle only when the heartbeat is stale (or has never been written) *and* no pty session
under `/dev/pts` has had activity within `threshold_s`.

For a poll loop, use `hangar.IdleWatchdog`, instantiated once at process start:

```python
from hangar import IdleWatchdog

watchdog = IdleWatchdog(threshold_s=20 * 60)

while True:
    if watchdog.poll():
        ...  # stop the pod
    time.sleep(30)
```

`IdleWatchdog`'s startup grace period reuses `threshold_s` rather than being a separate setting —
a fresh pod that hasn't written a heartbeat or opened an SSH session yet reads as "no signal," and
treating that as idle before the pod has had a chance to signal activity would shut it down
immediately. The grace period gives it one full threshold window to start signaling before idle
checks take effect.

## Max-runtime watchdog

`hangar-watchdog --max-hours N` sleeps for `N` hours, then stops its own pod via RunPod's API —
a last line of defense if whatever was supposed to tear the pod down (a local CLI's `finally`
block, a caller process) never runs, e.g. because the local machine or its network connection
died mid-run rather than the process exiting cleanly. It reads `RUNPOD_API_KEY`/`RUNPOD_POD_ID`
from the pod's own environment, both of which `start_pod`/`create_pod` already inject into every
pod, so no extra wiring is needed beyond starting it.

Start it detached inside the pod, the same way as `hangar-run` — typically over the same SSH
session that launches the real workload:

```
ssh pod-host 'nohup hangar-watchdog --max-hours 6 >/tmp/hangar-watchdog.log 2>&1 & disown'
```

It's independent of activity — unlike `IdleWatchdog` above, it fires on elapsed wall-clock time
alone, regardless of whether the pod is busy.

## Development

```
uv sync --extra dev
uv run pytest
```

Unit tests mock the RunPod API and don't require a real API key. There is no live-API test suite
in CI; real round-trip verification is done ad hoc against the actual RunPod API.
