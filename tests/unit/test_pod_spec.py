import httpx
import pytest

from hangar import runpod_client
from hangar.pod_spec import PodSpec, start_pod


@pytest.fixture(autouse=True)
def _api_key():
    original = runpod_client._api_key
    runpod_client._api_key = "test-runpod-key"
    yield
    runpod_client._api_key = original


def _spec(**overrides) -> PodSpec:
    defaults = dict(
        name="hangar-test",
        image="ghcr.io/example/hangar:latest",
        gpu_type_id="NVIDIA GeForce RTX 4090",
        disk_gb=20,
        ports=["8000/http"],
        device_env_key="HANGAR_DEVICE",
        device_env_value="cuda",
    )
    defaults.update(overrides)
    return PodSpec(**defaults)


def _fake_rest_client(monkeypatch, handler):
    def fake_rest_client():
        return httpx.Client(
            base_url="https://api.runpod.io/v2",
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr("hangar.runpod_client._rest_client", fake_rest_client)


def test_start_pod_resumes_existing_pod_id(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, str(request.url)))
        return httpx.Response(200, json={"id": "pod-existing"})

    _fake_rest_client(monkeypatch, handler)

    pod_id = start_pod(_spec(pod_id="pod-existing"))

    assert pod_id == "pod-existing"
    assert calls == [("POST", "https://api.runpod.io/v2/pods/pod-existing/action")]


def test_start_pod_creates_when_no_pod_id(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method + " " + request.url.path)
        return httpx.Response(200, json={"id": "pod-new"})

    _fake_rest_client(monkeypatch, handler)

    pod_id = start_pod(_spec(extra_env={"GATEWAY_API_KEY": "gw-secret"}))

    assert pod_id == "pod-new"
    assert "POST /v2/pods" in calls
    assert "PATCH /v2/pods/pod-new" in calls
    assert "POST /v2/pods/pod-new/action" in calls


def test_start_pod_falls_back_to_create_on_capacity_error(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method + " " + request.url.path)
        if request.url.path == "/v2/pods/pod-old/action":
            return httpx.Response(400, text="Error: not enough free GPUs on the host machine")
        return httpx.Response(200, json={"id": "pod-fresh"})

    _fake_rest_client(monkeypatch, handler)

    pod_id = start_pod(_spec(pod_id="pod-old"))

    assert pod_id == "pod-fresh"
    assert "DELETE /v2/pods/pod-old" in calls
    assert "POST /v2/pods" in calls


def test_start_pod_falls_back_to_create_when_pod_id_not_found(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method + " " + request.url.path)
        if request.url.path == "/v2/pods/pod-gone/action":
            return httpx.Response(404, text="Error: pod not found")
        return httpx.Response(200, json={"id": "pod-fresh"})

    _fake_rest_client(monkeypatch, handler)

    pod_id = start_pod(_spec(pod_id="pod-gone"))

    assert pod_id == "pod-fresh"
    assert "POST /v2/pods" in calls
    # No DELETE call: a pod RunPod already has no record of needs no cleanup.
    assert "DELETE /v2/pods/pod-gone" not in calls


def test_pod_env_merges_device_and_extra_env(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/pods":
            import json

            captured["create_env"] = json.loads(request.content)["env"]
        return httpx.Response(200, json={"id": "pod-new"})

    _fake_rest_client(monkeypatch, handler)

    start_pod(_spec(device_env_value="cuda", extra_env={"GATEWAY_API_KEY": "gw-secret"}))

    assert captured["create_env"] == {
        "RUNPOD_API_KEY": "test-runpod-key",
        "HANGAR_DEVICE": "cuda",
        "GATEWAY_API_KEY": "gw-secret",
    }
