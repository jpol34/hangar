"""Ad hoc real round-trip check against the actual RunPod API: create a pod, confirm it's
running, stop it, resume it, then terminate it. Prints each pod id and timestamp as it goes.

Requires RUNPOD_API_KEY in the environment — run via verify_live.ps1, which sources it from
Strongbox, rather than invoking this directly with a hardcoded key.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime

from hangar import PodCapacityError, delete_pod, get_pod, init, pod_action, start_pod
from hangar.pod_spec import PodSpec


def _ts() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def main() -> None:
    api_key = os.environ.get("RUNPOD_API_KEY")
    if not api_key:
        print("RUNPOD_API_KEY is not set in the environment.")
        raise SystemExit(1)

    init(api_key)

    spec = PodSpec(
        name="hangar-verify",
        image="runpod/base:0.6.2-cpu",
        gpu_type_id="NVIDIA GeForce RTX 4090",
        disk_gb=10,
        ports=["22/tcp"],
        device_env_key="HANGAR_VERIFY",
        device_env_value="1",
    )

    print(f"[{_ts()}] creating pod...")
    try:
        pod_id = start_pod(spec)
    except PodCapacityError as exc:
        print(f"[{_ts()}] capacity error on create: {exc}")
        raise SystemExit(1) from exc
    print(f"[{_ts()}] created pod {pod_id}")

    try:
        for _ in range(30):
            pod = get_pod(pod_id)
            status = (pod or {}).get("desiredStatus")
            print(f"[{_ts()}] pod {pod_id} status: {status}")
            if status == "RUNNING":
                break
            time.sleep(10)
        else:
            print(f"[{_ts()}] pod {pod_id} never reached RUNNING")
            raise SystemExit(1)

        print(f"[{_ts()}] stopping pod {pod_id}...")
        pod_action(pod_id, "stop")
        time.sleep(10)
        stopped_status = (get_pod(pod_id) or {}).get("desiredStatus")
        print(f"[{_ts()}] pod {pod_id} status after stop: {stopped_status}")

        print(f"[{_ts()}] resuming pod {pod_id} via start_pod (spec.pod_id set)...")
        spec.pod_id = pod_id
        resumed_id = start_pod(spec)
        print(f"[{_ts()}] resumed pod id: {resumed_id}")
        time.sleep(10)
        print(
            f"[{_ts()}] pod {resumed_id} status after resume: "
            f"{(get_pod(resumed_id) or {}).get('desiredStatus')}"
        )
    finally:
        print(f"[{_ts()}] cleaning up: terminating pod {pod_id}...")
        delete_pod(pod_id)
        print(f"[{_ts()}] pod {pod_id} deleted")


if __name__ == "__main__":
    main()
