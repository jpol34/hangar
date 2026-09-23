import os
import time

import pytest

from hangar import heartbeat, idle


@pytest.fixture
def heartbeat_file(tmp_path, monkeypatch):
    path = tmp_path / "hangar-heartbeat"
    monkeypatch.setenv("HANGAR_HEARTBEAT_FILE", str(path))
    return path


@pytest.fixture
def pts_dir(tmp_path, monkeypatch):
    d = tmp_path / "pts"
    d.mkdir()
    monkeypatch.setattr(idle, "_PTS_DIR", d)
    return d


def _age_file(path, age_s: float) -> None:
    when = time.time() - age_s
    os.utime(path, (when, when))


# -- get_heartbeat_age_s -----------------------------------------------------------------------


def test_get_heartbeat_age_s_none_when_missing(heartbeat_file):
    assert idle.get_heartbeat_age_s() is None


def test_get_heartbeat_age_s_reflects_mtime(heartbeat_file):
    heartbeat.touch_heartbeat()
    _age_file(heartbeat_file, 42.0)

    age = idle.get_heartbeat_age_s()

    assert age == pytest.approx(42.0, abs=1.0)


# -- get_ssh_idle_s -----------------------------------------------------------------------------


def test_get_ssh_idle_s_none_when_no_sessions(pts_dir):
    assert idle.get_ssh_idle_s() is None


def test_get_ssh_idle_s_skips_non_numeric_entries(pts_dir):
    (pts_dir / "ptmx").touch()

    assert idle.get_ssh_idle_s() is None


def test_get_ssh_idle_s_returns_minimum_age(pts_dir):
    old = pts_dir / "0"
    fresh = pts_dir / "1"
    old.touch()
    fresh.touch()
    _atime_only(old, 300.0)
    _atime_only(fresh, 5.0)

    age = idle.get_ssh_idle_s()

    assert age == pytest.approx(5.0, abs=1.0)


def _atime_only(path, age_s: float) -> None:
    mtime = path.stat().st_mtime
    when = time.time() - age_s
    os.utime(path, (when, mtime))


# -- is_idle: heartbeat fresh/stale x ssh fresh/stale/no-signal truth table ---------------------


def test_is_idle_false_when_heartbeat_fresh_no_ssh(heartbeat_file, pts_dir):
    heartbeat.touch_heartbeat()

    assert idle.is_idle(threshold_s=60) is False


def test_is_idle_false_when_ssh_fresh_no_heartbeat(heartbeat_file, pts_dir):
    session = pts_dir / "0"
    session.touch()

    assert idle.is_idle(threshold_s=60) is False


def test_is_idle_false_when_both_fresh(heartbeat_file, pts_dir):
    heartbeat.touch_heartbeat()
    (pts_dir / "0").touch()

    assert idle.is_idle(threshold_s=60) is False


def test_is_idle_true_when_both_stale(heartbeat_file, pts_dir):
    heartbeat.touch_heartbeat()
    _age_file(heartbeat_file, 300.0)
    session = pts_dir / "0"
    session.touch()
    _atime_only(session, 300.0)

    assert idle.is_idle(threshold_s=60) is True


def test_is_idle_true_when_no_signal_at_all(heartbeat_file, pts_dir):
    assert idle.is_idle(threshold_s=60) is True


def test_is_idle_false_when_heartbeat_stale_but_ssh_fresh(heartbeat_file, pts_dir):
    heartbeat.touch_heartbeat()
    _age_file(heartbeat_file, 300.0)
    (pts_dir / "0").touch()

    assert idle.is_idle(threshold_s=60) is False


# -- IdleWatchdog -------------------------------------------------------------------------------


def test_idle_watchdog_not_idle_during_grace_period(heartbeat_file, pts_dir):
    watchdog = idle.IdleWatchdog(threshold_s=60)

    assert watchdog.poll() is False


def test_idle_watchdog_idle_after_grace_period_with_no_signal(heartbeat_file, pts_dir):
    watchdog = idle.IdleWatchdog(threshold_s=60)
    watchdog._started_at -= 61

    assert watchdog.poll() is True


def test_idle_watchdog_not_idle_after_grace_period_with_fresh_heartbeat(heartbeat_file, pts_dir):
    watchdog = idle.IdleWatchdog(threshold_s=60)
    watchdog._started_at -= 61
    heartbeat.touch_heartbeat()

    assert watchdog.poll() is False
