import os
import time

import pytest

from hangar.middleware import HeartbeatMiddleware


@pytest.fixture
def heartbeat_file(tmp_path, monkeypatch):
    path = tmp_path / "hangar-heartbeat"
    monkeypatch.setenv("HANGAR_HEARTBEAT_FILE", str(path))
    return path


async def _noop_receive():
    return {"type": "http.request"}


class _RecordingSend:
    def __init__(self):
        self.messages = []

    async def __call__(self, message):
        self.messages.append(message)


async def _call_app_recording(scope):
    calls = []

    async def app(scope, receive, send):
        calls.append(scope)

    middleware = HeartbeatMiddleware(app)
    await middleware(scope, _noop_receive, _RecordingSend())
    return calls


@pytest.mark.asyncio
async def test_lifespan_scope_passed_through_untouched(heartbeat_file):
    calls = await _call_app_recording({"type": "lifespan"})

    assert calls == [{"type": "lifespan"}]
    assert not heartbeat_file.exists()


@pytest.mark.asyncio
async def test_websocket_scope_passed_through_untouched(heartbeat_file):
    calls = await _call_app_recording({"type": "websocket", "path": "/ws"})

    assert calls == [{"type": "websocket", "path": "/ws"}]
    assert not heartbeat_file.exists()


@pytest.mark.asyncio
async def test_http_request_touches_heartbeat(heartbeat_file):
    async def app(scope, receive, send):
        pass

    middleware = HeartbeatMiddleware(app)
    await middleware({"type": "http", "path": "/work"}, _noop_receive, _RecordingSend())

    assert heartbeat_file.exists()


@pytest.mark.asyncio
async def test_excluded_path_does_not_touch_heartbeat(heartbeat_file):
    async def app(scope, receive, send):
        pass

    middleware = HeartbeatMiddleware(app, exclude_paths=["/healthz"])
    await middleware({"type": "http", "path": "/healthz"}, _noop_receive, _RecordingSend())

    assert not heartbeat_file.exists()


@pytest.mark.asyncio
async def test_excluded_path_still_calls_app(heartbeat_file):
    calls = []

    async def app(scope, receive, send):
        calls.append(scope["path"])

    middleware = HeartbeatMiddleware(app, exclude_paths=["/healthz"])
    await middleware({"type": "http", "path": "/healthz"}, _noop_receive, _RecordingSend())

    assert calls == ["/healthz"]


@pytest.mark.asyncio
async def test_rate_limits_writes_within_freshness_window(heartbeat_file):
    async def app(scope, receive, send):
        pass

    middleware = HeartbeatMiddleware(app, interval_s=30.0)
    await middleware({"type": "http", "path": "/work"}, _noop_receive, _RecordingSend())
    first_mtime = heartbeat_file.stat().st_mtime

    # Well within the freshness window (a third of interval_s == 10s) -> no second write.
    await middleware({"type": "http", "path": "/work"}, _noop_receive, _RecordingSend())
    second_mtime = heartbeat_file.stat().st_mtime

    assert first_mtime == second_mtime


@pytest.mark.asyncio
async def test_writes_again_once_stale(heartbeat_file):
    async def app(scope, receive, send):
        pass

    middleware = HeartbeatMiddleware(app, interval_s=30.0)
    await middleware({"type": "http", "path": "/work"}, _noop_receive, _RecordingSend())

    stale_mtime = time.time() - 100
    os.utime(heartbeat_file, (stale_mtime, stale_mtime))

    await middleware({"type": "http", "path": "/work"}, _noop_receive, _RecordingSend())

    assert heartbeat_file.stat().st_mtime > stale_mtime
