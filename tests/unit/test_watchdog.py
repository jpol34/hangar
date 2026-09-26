import sys

import httpx
import pytest

from hangar import runpod_client, watchdog


@pytest.fixture(autouse=True)
def _api_key():
    original = runpod_client._api_key
    yield
    runpod_client._api_key = original


def _fake_graphql(monkeypatch, handler):
    def fake_post(url, **kwargs):
        request = httpx.Request("POST", url)
        response = handler(request, kwargs)
        response.request = request
        return response

    monkeypatch.setattr("hangar.runpod_client.httpx.post", fake_post)


def test_main_requires_runpod_api_key(monkeypatch, capsys):
    monkeypatch.delenv("RUNPOD_API_KEY", raising=False)
    monkeypatch.setenv("RUNPOD_POD_ID", "pod-123")
    monkeypatch.setattr(sys, "argv", ["hangar-watchdog", "--max-hours", "6"])

    with pytest.raises(SystemExit) as exc_info:
        watchdog.main()

    assert exc_info.value.code == 2
    assert "RUNPOD_API_KEY" in capsys.readouterr().err


def test_main_requires_runpod_pod_id(monkeypatch, capsys):
    monkeypatch.setenv("RUNPOD_API_KEY", "test-key")
    monkeypatch.delenv("RUNPOD_POD_ID", raising=False)
    monkeypatch.setattr(sys, "argv", ["hangar-watchdog", "--max-hours", "6"])

    with pytest.raises(SystemExit) as exc_info:
        watchdog.main()

    assert exc_info.value.code == 2
    assert "RUNPOD_POD_ID" in capsys.readouterr().err


def test_main_requires_max_hours(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "test-key")
    monkeypatch.setenv("RUNPOD_POD_ID", "pod-123")
    monkeypatch.setattr(sys, "argv", ["hangar-watchdog"])

    with pytest.raises(SystemExit) as exc_info:
        watchdog.main()

    assert exc_info.value.code == 2


def test_main_sleeps_then_stops_its_own_pod(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "test-key")
    monkeypatch.setenv("RUNPOD_POD_ID", "pod-123")
    monkeypatch.setattr(sys, "argv", ["hangar-watchdog", "--max-hours", "6"])

    slept = {}

    def fake_sleep(seconds):
        slept["seconds"] = seconds

    monkeypatch.setattr(watchdog.time, "sleep", fake_sleep)

    def handler(request: httpx.Request, kwargs) -> httpx.Response:
        assert "podStop" in kwargs["json"]["query"]
        assert "pod-123" in kwargs["json"]["query"]
        return httpx.Response(
            200, json={"data": {"podStop": {"id": "pod-123", "desiredStatus": "EXITED"}}}
        )

    _fake_graphql(monkeypatch, handler)

    watchdog.main()

    assert slept["seconds"] == 6 * 3600
    assert runpod_client._api_key == "test-key"
