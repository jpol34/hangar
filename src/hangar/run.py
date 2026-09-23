"""`hangar-run <command>`: wraps a subprocess and keeps the shared heartbeat file fresh for as
long as it's alive, so process-liveness alone is enough to signal activity — zero code changes
needed in whatever it wraps.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading

from hangar.heartbeat import touch_heartbeat

DEFAULT_INTERVAL_S = 30.0


def _tick(interval_s: float, stop: threading.Event) -> None:
    while not stop.wait(interval_s):
        touch_heartbeat()


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: hangar-run <command> [args...]", file=sys.stderr)
        sys.exit(2)

    interval_s = float(os.environ.get("HANGAR_HEARTBEAT_INTERVAL_S", DEFAULT_INTERVAL_S))

    # Touched once immediately so a fresh pod isn't falsely idle before the first background tick.
    touch_heartbeat()

    stop = threading.Event()
    ticker = threading.Thread(target=_tick, args=(interval_s, stop), daemon=True)
    ticker.start()
    try:
        result = subprocess.run(sys.argv[1:])
    finally:
        stop.set()
        ticker.join()

    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
