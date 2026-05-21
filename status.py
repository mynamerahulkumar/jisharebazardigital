from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parent
ENTRYPOINTS = ("start.py", "main.py")
LOG_DIR = REPO_ROOT / "logs"
LOG_FILES = (
    ("CLI", LOG_DIR / "cli.log"),
    ("SYSTEM", LOG_DIR / "system.log"),
    ("TRADING", LOG_DIR / "trading.log"),
    ("ERROR", LOG_DIR / "error.log"),
)
FOLLOW_INTERVAL_SECONDS = 1.0
IST = ZoneInfo("Asia/Kolkata")
LOG_TIMESTAMP_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) IST\]")


def process_rows() -> list[tuple[int, str, str]]:
    result = subprocess.run(
        ["ps", "-axo", "pid=,etime=,command="],
        check=True,
        capture_output=True,
        text=True,
    )

    rows: list[tuple[int, str, str]] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(None, 2)
        if len(parts) < 3:
            continue
        pid_text, elapsed, command = parts
        try:
            rows.append((int(pid_text), elapsed, command.strip()))
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
    tokens = command_tokens(command)
    token_names = {Path(token).name for token in tokens}
    if "status.py" in token_names or "stop.py" in token_names:
        return False

    script_paths = {str((REPO_ROOT / entrypoint).resolve()) for entrypoint in ENTRYPOINTS}
    if any(token in script_paths for token in tokens):
        return True

    if not any(token_name in ENTRYPOINTS for token_name in token_names):
        return False

    cwd = process_cwd(pid)
    if cwd is None:
        return False

    return cwd == REPO_ROOT


def find_bot_processes() -> list[tuple[int, str, str]]:
    current_pid = os.getpid()
    return [
        (pid, elapsed, command)
        for pid, elapsed, command in process_rows()
        if pid != current_pid and references_this_bot(pid, command)
    ]


def elapsed_to_seconds(elapsed: str) -> int | None:
    try:
        day_part, _, clock_part = elapsed.partition("-")
        days = int(day_part) if clock_part else 0
        clock = clock_part or day_part
        parts = [int(part) for part in clock.split(":")]
    except ValueError:
        return None

    if len(parts) == 2:
        hours = 0
        minutes, seconds = parts
    elif len(parts) == 3:
        hours, minutes, seconds = parts
    else:
        return None

    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def current_run_started_at(matches: list[tuple[int, str, str]]) -> float | None:
    started_at: list[float] = []
    now = time.time()
    for _, elapsed, _ in matches:
        elapsed_seconds = elapsed_to_seconds(elapsed)
        if elapsed_seconds is not None:
            started_at.append(now - elapsed_seconds)
    return min(started_at) if started_at else None


def latest_logged_start_at() -> float | None:
    latest_start: float | None = None
    for line in tail_lines(LOG_DIR / "system.log", 300):
        if "Connecting websocket:" not in line:
            continue
        timestamp = timestamp_from_log_line(line)
        if timestamp is not None:
            latest_start = timestamp
    return latest_start


def tail_lines(path: Path, line_count: int) -> list[str]:
    if line_count <= 0:
        return []
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        lines = handle.readlines()
    return [line.rstrip("\n") for line in lines[-line_count:]]


def timestamp_from_log_line(line: str) -> float | None:
    match = LOG_TIMESTAMP_RE.match(line)
    if match is None:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST).timestamp()
    except ValueError:
        return None


def tail_error_lines_for_current_run(path: Path, line_count: int, started_at: float | None) -> list[str]:
    if started_at is None:
        return tail_lines(path, line_count)

    lines = tail_lines(path, max(line_count * 5, 300))
    recent_lines: list[str] = []
    current_block: list[str] = []
    current_block_is_recent = False

    for line in lines:
        timestamp = timestamp_from_log_line(line)
        if timestamp is not None:
            if current_block and current_block_is_recent:
                recent_lines.extend(current_block)
            current_block = [line]
            current_block_is_recent = timestamp >= started_at
            continue
        if current_block:
            current_block.append(line)

    if current_block and current_block_is_recent:
        recent_lines.extend(current_block)

    return recent_lines[-line_count:]


def print_section(title: str) -> None:
    print(f"\n=== {title} ===")


def print_status(matches: list[tuple[int, str, str]]) -> None:
    print_section("BOT STATUS")
    if not matches:
        print("Status: STOPPED")
        print("No running trading bot process found.")
        return

    print("Status: RUNNING")
    for pid, elapsed, command in matches:
        print(f"PID: {pid}")
        print(f"Uptime: {elapsed}")
        print(f"Command: {command}")


def print_logs(line_count: int, include_app_logs: bool, current_started_at: float | None) -> None:
    selected_logs = LOG_FILES if include_app_logs else LOG_FILES[:1]
    for title, path in selected_logs:
        print_section(f"{title} LOG ({path.relative_to(REPO_ROOT)})")
        if title == "ERROR":
            lines = tail_error_lines_for_current_run(path, line_count, current_started_at)
        else:
            lines = tail_lines(path, line_count)
        if not lines:
            if title == "ERROR" and current_started_at is not None:
                print("No error output found for the current bot run.")
            else:
                print("No log output found.")
            continue
        for line in lines:
            print(line)


def iter_follow_paths(include_app_logs: bool) -> Iterator[tuple[str, Path]]:
    yield from (LOG_FILES if include_app_logs else LOG_FILES[:1])


def follow_logs(include_app_logs: bool) -> None:
    print_section("FOLLOWING LOGS")
    print("Press Ctrl+C to stop.")

    positions: dict[Path, int] = {}
    for _, path in iter_follow_paths(include_app_logs):
        if path.exists():
            positions[path] = path.stat().st_size
        else:
            positions[path] = 0

    try:
        while True:
            for title, path in iter_follow_paths(include_app_logs):
                if not path.exists():
                    continue
                with path.open("r", encoding="utf-8", errors="replace") as handle:
                    handle.seek(positions.get(path, 0))
                    chunk = handle.read()
                    positions[path] = handle.tell()
                if chunk:
                    for line in chunk.rstrip("\n").splitlines():
                        print(f"[{title}] {line}")
            time.sleep(FOLLOW_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nStopped following logs.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show trading bot status and recent logs.")
    parser.add_argument("--lines", type=int, default=40, help="Number of recent lines to show from each log.")
    parser.add_argument(
        "--no-app-logs",
        action="store_true",
        help="Only show the captured CLI/dashboard log, not system/trading/error logs.",
    )
    parser.add_argument("--follow", action="store_true", help="Keep printing new log lines until Ctrl+C.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    matches = find_bot_processes()
    include_app_logs = not args.no_app_logs
    current_started_at = current_run_started_at(matches) or latest_logged_start_at()

    print_status(matches)
    print_logs(args.lines, include_app_logs, current_started_at)
    if args.follow:
        follow_logs(include_app_logs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
