"""Idle-detection: combines heartbeat freshness with SSH/tty activity via OR semantics — a pod is
considered idle only when both signals are stale (or absent). Heartbeat-writing lives in
`hangar.heartbeat`; this module only reads signals back.

SSH-idle detection uses Linux's native per-tty idle tracking (pty device access time), the same
technique standard cloud-dev idle-shutdown tools use.
"""

from __future__ import annotations

import time
from pathlib import Path

from hangar.heartbeat import heartbeat_path

_PTS_DIR = Path("/dev/pts")


def get_heartbeat_age_s() -> float | None:
    """Seconds since the heartbeat file was last touched, or None if it hasn't been written yet."""
    try:
        mtime = heartbeat_path().stat().st_mtime
    except OSError:
        return None
    return max(0.0, time.time() - mtime)


def get_ssh_idle_s() -> float | None:
    """Seconds since the most recently active open pty session, or None if none are open.

    Enumerates numeric-named entries under `/dev/pts` (each open SSH/tty session gets one) and
    returns the minimum access-time age across them, skipping non-numeric entries like `ptmx`.

    Under the default `relatime` mount option, atime only advances when it's already older than
    mtime/ctime or more than a day stale — the same coarse granularity `w`/`who -u` rely on for
    this technique. In practice a pty's mtime also moves on every write (terminal echo), which
    keeps atime tracking real activity closely enough for idle-threshold purposes.
    """
    try:
        entries = list(_PTS_DIR.iterdir())
    except OSError:
        return None

    now = time.time()
    ages: list[float] = []
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            atime = entry.stat().st_atime
        except OSError:
            continue
        ages.append(max(0.0, now - atime))

    return min(ages) if ages else None


def is_idle(threshold_s: float) -> bool:
    """Not idle if the heartbeat is fresh within `threshold_s` OR an SSH/tty session has had
    activity within that same window. No signal at all (neither has ever fired) reads as idle."""
    heartbeat_age = get_heartbeat_age_s()
    if heartbeat_age is not None and heartbeat_age < threshold_s:
        return False

    ssh_idle = get_ssh_idle_s()
    if ssh_idle is not None and ssh_idle < threshold_s:
        return False

    return True


class IdleWatchdog:
    """Instantiate once at process start; call `poll()` each iteration of a caller's poll loop.

    Applies its own startup grace period so a fresh pod that hasn't signaled activity yet (no
    heartbeat written, no SSH session opened) isn't immediately treated as idle. The grace period
    reuses `threshold_s` rather than being a second config knob.
    """

    def __init__(self, threshold_s: float):
        self.threshold_s = threshold_s
        self._started_at = time.monotonic()

    def poll(self) -> bool:
        """Returns whether the pod should be considered idle right now."""
        if time.monotonic() - self._started_at < self.threshold_s:
            return False
        return is_idle(self.threshold_s)
