"""`PodSpec` + `start_pod`: resume an existing pod if it has a `pod_id`, otherwise create a fresh
one, falling back to terminate-and-recreate when the pinned host has no free GPU capacity for a
resume/start."""

from __future__ import annotations

from dataclasses import dataclass, field

from hangar.runpod_client import (
    PodCapacityError,
    PodNotFoundError,
    _require_api_key,
    create_network_volume,
    create_pod,
    delete_pod,
    get_network_volume,
    pod_action,
    update_pod_env,
)


@dataclass
class PodSpec:
    """Describes the pod a caller wants running. `pod_id`, when set, is resumed instead of
    creating a new pod; on a capacity failure, or if RunPod no longer knows about that pod id
    (already deleted), a fresh pod is created instead.

    `device_env_key`/`device_env_value` sets a single project-specific device env var (e.g.
    `TRELLIS_DEVICE=cuda`). `extra_env` carries any other env vars the pod's entrypoint needs
    (e.g. a gateway API key) and is merged in as-is — this library does not validate its
    contents, since which keys are required is caller-specific.
    """

    name: str
    image: str
    gpu_type_id: str
    disk_gb: int
    ports: list[str]
    device_env_key: str
    device_env_value: str
    pod_id: str | None = None
    extra_env: dict[str, str] = field(default_factory=dict)
    registry_id: str = ""
    data_center_id: str | None = None
    network_volume_id: str | None = None
    network_volume_mount_path: str | None = None


def _pod_env(spec: PodSpec, api_key: str) -> dict[str, str]:
    return {
        "RUNPOD_API_KEY": api_key,
        spec.device_env_key: spec.device_env_value,
        **spec.extra_env,
    }


def _create_pod(spec: PodSpec, api_key: str) -> str:
    result = create_pod(
        name=spec.name,
        image=spec.image,
        gpu_id=spec.gpu_type_id,
        disk_gb=spec.disk_gb,
        ports=spec.ports,
        env=_pod_env(spec, api_key),
        registry_id=spec.registry_id,
        data_center_id=spec.data_center_id,
        network_volume_id=spec.network_volume_id,
        network_volume_mount_path=spec.network_volume_mount_path,
    )
    pod_id = result["id"]
    # RUNPOD_POD_ID can't be known until the pod exists, so it's set after creation and the pod
    # is restarted to pick it up — env vars are baked in at container start. The RunPod API's
    # pod-env PATCH replaces the whole env map rather than merging, so this must resend every
    # key from _pod_env(), not just the new one.
    update_pod_env(pod_id, {**_pod_env(spec, api_key), "RUNPOD_POD_ID": pod_id})
    pod_action(pod_id, "restart")
    return pod_id


def start_pod(spec: PodSpec) -> str:
    """Resumes `spec.pod_id` if set, otherwise creates a fresh pod. Returns the running pod's
    id. Requires `hangar.runpod_client.init(api_key)` to have been called first."""
    api_key = _require_api_key()

    if spec.pod_id:
        try:
            pod_action(spec.pod_id, "start")
            return spec.pod_id
        except PodCapacityError:
            delete_pod(spec.pod_id)
            return _create_pod(spec, api_key)
        except PodNotFoundError:
            return _create_pod(spec, api_key)

    return _create_pod(spec, api_key)


def ensure_network_volume(
    *, name: str, size_gb: int, data_center_id: str, volume_id: str | None = None
) -> str:
    """Resumes `volume_id` if it still resolves, otherwise creates a fresh network volume.
    Returns the volume's id. Requires `hangar.runpod_client.init(api_key)` to have been called
    first."""
    _require_api_key()

    if volume_id and get_network_volume(volume_id):
        return volume_id

    result = create_network_volume(name=name, size_gb=size_gb, data_center_id=data_center_id)
    return result["id"]
