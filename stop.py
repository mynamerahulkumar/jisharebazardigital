from __future__ import annotations

import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
ENTRYPOINTS = ("start.py", "main.py")
STOP_TIMEOUT_SECONDS = 10.0
POLL_INTERVAL_SECONDS = 0.25


def process_rows() -> list[tuple[int, str]]:
    result = subprocess.run(
        ["ps", "-axo", "pid=,command="],
        check=True,
        capture_output=True,
        text=True,
    )

    rows: list[tuple[int, str]] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_text, _, command = stripped.partition(" ")
        if not command:
            continue
        try:
            rows.append((int(pid_text), command.strip()))
        except ValueError:
            continue
    return rows


def process_cwd(pid: int) -> Path | None:
    proc_cwd = Path(f"/proc/{pid}/cwd")
    if proc_cwd.exists():
        try:
            return proc_cwd.resolve()
        except OSError:
            return None

    try:
        result = subprocess.run(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None

    for line in result.stdout.splitlines():
        if line.startswith("n"):
            return Path(line[1:]).resolve()
    return None


def command_tokens(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def references_this_bot(pid: int, command: str) -> bool:
    script_paths = {str((REPO_ROOT / entrypoint).resolve()) for entrypoint in ENTRYPOINTS}
    if any(script_path in command for script_path in script_paths):
        return True

    tokens = command_tokens(command)
    if not any(Path(token).name in ENTRYPOINTS for token in tokens):
        return False

    cwd = process_cwd(pid)
    if cwd is None:
        return False

    return cwd == REPO_ROOT


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
    current_pid = os.getpid()
    matches = [
        (pid, command)
        for pid, command in process_rows()
        if pid != current_pid and references_this_bot(pid, command)
    ]

    if not matches:
        print("No running trading bot process found.")
        return 0

    results = [stop_process(pid, command) for pid, command in matches]
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
