"""Shared heartbeat file convention. `touch_heartbeat()` records activity by updating a single
file's mtime; `hangar.idle` reads that file back to decide whether anything is active.

The file path defaults to `/tmp/hangar-heartbeat` and is overridable via the
`HANGAR_HEARTBEAT_FILE` env var so tests and multi-pod setups can point it elsewhere.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_HEARTBEAT_FILE = "/tmp/hangar-heartbeat"

# O_NOFOLLOW and utime's follow_symlinks=False guard against a symlink planted at the heartbeat
# path redirecting the write to an arbitrary target. Both are Linux-only (the deployment target,
# RunPod pods); on platforms without them the write just follows symlinks as os.utime always did.
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def heartbeat_path() -> Path:
    """The heartbeat file path, honoring `HANGAR_HEARTBEAT_FILE` if set."""
    return Path(os.environ.get("HANGAR_HEARTBEAT_FILE", DEFAULT_HEARTBEAT_FILE))


def _utime_now(path: Path) -> None:
    try:
        os.utime(path, None, follow_symlinks=False)
    except NotImplementedError:
        os.utime(path, None)


def touch_heartbeat() -> None:
    """Records activity by setting the heartbeat file's mtime to now.

    This is a single atomic `os.utime()` call on the common path, since the file is written
    concurrently by a background thread, an async event loop, and read concurrently by a separate
    watchdog process. If the file doesn't exist yet, it's created (never truncated) before
    retrying the `utime` call.
    """
    path = heartbeat_path()
    try:
        _utime_now(path)
    except FileNotFoundError:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | _O_NOFOLLOW, 0o600)
            os.close(fd)
        except FileExistsError:
            pass
        _utime_now(path)
