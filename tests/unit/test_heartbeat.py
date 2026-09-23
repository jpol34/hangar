import os
import sys
import threading
import time

import pytest

from hangar import heartbeat


@pytest.fixture
def heartbeat_file(tmp_path, monkeypatch):
    path = tmp_path / "hangar-heartbeat"
    monkeypatch.setenv("HANGAR_HEARTBEAT_FILE", str(path))
    return path


def test_heartbeat_path_honors_env_override(heartbeat_file):
    assert heartbeat.heartbeat_path() == heartbeat_file


def test_touch_heartbeat_creates_file_if_missing(heartbeat_file):
    assert not heartbeat_file.exists()

    heartbeat.touch_heartbeat()

    assert heartbeat_file.exists()


def test_touch_heartbeat_updates_mtime_on_existing_file(heartbeat_file):
    heartbeat.touch_heartbeat()
    first_mtime = heartbeat_file.stat().st_mtime

    time.sleep(0.05)
    heartbeat.touch_heartbeat()
    second_mtime = heartbeat_file.stat().st_mtime

    assert second_mtime > first_mtime


def test_touch_heartbeat_concurrent_writers_dont_raise(heartbeat_file):
    errors: list[BaseException] = []

    def hammer():
        try:
            for _ in range(50):
                heartbeat.touch_heartbeat()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=hammer) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert heartbeat_file.exists()
    # A valid, recent mtime resulted from the concurrent hammering.
    assert time.time() - heartbeat_file.stat().st_mtime < 5.0


@pytest.mark.skipif(sys.platform == "win32", reason="symlink hardening is Linux-only")
def test_touch_heartbeat_does_not_follow_a_planted_symlink(tmp_path, heartbeat_file):
    target = tmp_path / "attacker-target"
    target.touch()
    target_mtime_before = target.stat().st_mtime

    os.symlink(target, heartbeat_file)
    heartbeat.touch_heartbeat()

    assert target.stat().st_mtime == target_mtime_before
    assert os.path.islink(heartbeat_file)
