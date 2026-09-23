"""Dependency-free ASGI middleware that touches the shared heartbeat file on real inbound HTTP
requests. Takes no dependency on fastapi/starlette — it's a plain ASGI callable wrapping another
one.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from hangar.heartbeat import heartbeat_path, touch_heartbeat

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class HeartbeatMiddleware:
    """Touches the heartbeat file on `http` requests whose path isn't excluded, rate-limited by a
    cheap `stat()` freshness check so it doesn't write on every single request. `lifespan` and
    `websocket` scopes are passed through untouched.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        interval_s: float = 30.0,
        exclude_paths: Iterable[str] = (),
    ):
        self._app = app
        self._interval_s = interval_s
        self._exclude_paths = frozenset(exclude_paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in self._exclude_paths:
            await self._app(scope, receive, send)
            return

        self._maybe_touch()
        await self._app(scope, receive, send)

    def _maybe_touch(self) -> None:
        # A third of the interval: fresh enough that skipping the write can't let the heartbeat
        # go stale before the next request has a chance to touch it again.
        fresh_within_s = self._interval_s / 3
        try:
            age = time.time() - heartbeat_path().stat().st_mtime
        except OSError:
            age = None

        if age is None or age >= fresh_within_s:
            touch_heartbeat()
