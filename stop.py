from __future__ import annotations

import os
import signal
import sys
import time

from utils.bot_cli import format_trading_plan, resolve_trading_plan
from utils.bot_process import find_bot_processes


STOP_TIMEOUT_SECONDS = 10.0
POLL_INTERVAL_SECONDS = 0.25


def is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_for_exit(pid: int, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not is_running(pid):
            return True
        time.sleep(POLL_INTERVAL_SECONDS)
    return not is_running(pid)


def stop_process(pid: int, command: str) -> bool:
    print(f"Stopping PID {pid}: {command}")
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        print(f"PID {pid} already stopped")
        return True
    except PermissionError:
        print(f"Permission denied stopping PID {pid}", file=sys.stderr)
        return False

    if wait_for_exit(pid, STOP_TIMEOUT_SECONDS):
        print(f"PID {pid} stopped")
        return True

    print(f"PID {pid} did not stop within {STOP_TIMEOUT_SECONDS:.0f}s", file=sys.stderr)
    return False


def main() -> int:
    try:
        symbols, summary = resolve_trading_plan()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(format_trading_plan(symbols, summary))
    matches = find_bot_processes()

    if not matches:
        print("No running trading bot process found.")
        return 0

    results = [stop_process(pid, command) for pid, command in matches]
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
