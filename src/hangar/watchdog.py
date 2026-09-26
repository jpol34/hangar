"""`hangar-watchdog --max-hours N`: a dumb, activity-independent ceiling on how long a pod can run,
started detached inside the pod (e.g. alongside `hangar-run` over the same SSH session that
launches the real workload). Sleeps for the given duration, then stops its own pod via RunPod's
API -- the last line of defense if whatever was supposed to tear the pod down (a local CLI's
`finally` block, a caller process) never runs, e.g. because the local machine or its network
connection died mid-run rather than the process exiting cleanly.

Reads `RUNPOD_API_KEY`/`RUNPOD_POD_ID` from the pod's own environment -- both are already injected
into every pod's env by `hangar.pod_spec._pod_env`, so no extra wiring is needed to use this.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from hangar.runpod_client import init, stop_pod


def main() -> None:
    parser = argparse.ArgumentParser(prog="hangar-watchdog")
    parser.add_argument("--max-hours", type=float, required=True)
    args = parser.parse_args()

    api_key = os.environ.get("RUNPOD_API_KEY")
    pod_id = os.environ.get("RUNPOD_POD_ID")
    if not api_key or not pod_id:
        print(
            "hangar-watchdog: RUNPOD_API_KEY and RUNPOD_POD_ID must both be set in the pod's "
            "environment",
            file=sys.stderr,
        )
        sys.exit(2)

    time.sleep(args.max_hours * 3600)

    print(f"hangar-watchdog: {args.max_hours}h elapsed, stopping pod {pod_id}", file=sys.stderr)
    init(api_key)
    stop_pod(pod_id)


if __name__ == "__main__":
    main()
