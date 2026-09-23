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

## Development

```
uv sync --extra dev
uv run pytest
```

Unit tests mock the RunPod API and don't require a real API key. There is no live-API test suite
in CI; real round-trip verification is done ad hoc against the actual RunPod API.
