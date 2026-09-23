import sys

import pytest

from hangar import run


@pytest.fixture
def heartbeat_file(tmp_path, monkeypatch):
    path = tmp_path / "hangar-heartbeat"
    monkeypatch.setenv("HANGAR_HEARTBEAT_FILE", str(path))
    return path


def test_main_exits_zero_and_touches_heartbeat(heartbeat_file, monkeypatch):
    monkeypatch.setattr(
        sys, "argv", ["hangar-run", sys.executable, "-c", "import sys; sys.exit(0)"]
    )

    with pytest.raises(SystemExit) as exc_info:
        run.main()

    assert exc_info.value.code == 0
    assert heartbeat_file.exists()


def test_main_mirrors_nonzero_exit_code(heartbeat_file, monkeypatch):
    monkeypatch.setattr(
        sys, "argv", ["hangar-run", sys.executable, "-c", "import sys; sys.exit(7)"]
    )

    with pytest.raises(SystemExit) as exc_info:
        run.main()

    assert exc_info.value.code == 7


def test_main_requires_a_command(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["hangar-run"])

    with pytest.raises(SystemExit) as exc_info:
        run.main()

    assert exc_info.value.code == 2
    assert "usage" in capsys.readouterr().err
