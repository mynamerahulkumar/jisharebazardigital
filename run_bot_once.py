"""Start the same trading bot as start.py in the background, then tail CLI output briefly.

The detached child runs start.py → main.main() → TradingBot (identical code path to running
start.py directly). Market entries and Delta bracket TP/SL happen only when the strategy
signals; see logs/trading.log for ENTRY+BRACKET / bracket attach lines, not only this tail.

This script: (1) starts start.py detached if no matching process exists, (2) prints new lines
from logs/cli.log for a configurable duration, (3) exits without stopping the bot.

Run from the repository root so `import utils.helpers` resolves (e.g. `uv run run_bot_once.py`).
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

from utils.helpers import load_config


REPO_ROOT = Path(__file__).resolve().parent
ENTRYPOINTS = ("start.py", "main.py")
SCRIPT_NAME = Path(__file__).name
LOG_DIR = REPO_ROOT / "logs"
CLI_LOG_PATH = LOG_DIR / "cli.log"
DEFAULT_FOLLOW_SECONDS = 30.0
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
    tokens = command_tokens(command)
    token_names = {Path(token).name for token in tokens}
    ignored_scripts = {SCRIPT_NAME, "status.py", "stop.py"}
    if token_names & ignored_scripts:
        return False

    script_paths = {str((REPO_ROOT / entrypoint).resolve()) for entrypoint in ENTRYPOINTS}
    if any(script_path in command for script_path in script_paths):
        return True

    if not any(token_name in ENTRYPOINTS for token_name in token_names):
        return False

    cwd = process_cwd(pid)
    if cwd is None:
        return False

    return cwd == REPO_ROOT


def find_bot_processes() -> list[tuple[int, str]]:
    current_pid = os.getpid()
    return [
        (pid, command)
        for pid, command in process_rows()
        if pid != current_pid and references_this_bot(pid, command)
    ]


def start_bot_detached() -> int:
    LOG_DIR.mkdir(exist_ok=True)

    with Path(os.devnull).open("r") as stdin, Path(os.devnull).open("a") as devnull:
        process = subprocess.Popen(
            [sys.executable, "-u", str(REPO_ROOT / "start.py")],
            cwd=REPO_ROOT,
            stdin=stdin,
            stdout=devnull,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )

    return process.pid


def print_bot_processes(matches: list[tuple[int, str]]) -> None:
    for pid, command in matches:
        print(f"PID: {pid}")
        print(f"Command: {command}")


def follow_cli_log(seconds: float) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    CLI_LOG_PATH.touch(exist_ok=True)

    deadline = time.monotonic() + seconds
    position = CLI_LOG_PATH.stat().st_size
    print(f"\n=== CLI LOG ({CLI_LOG_PATH.relative_to(REPO_ROOT)}) ===")
    print(f"Printing new CLI log output for {seconds:g} seconds.")

    while time.monotonic() < deadline:
        with CLI_LOG_PATH.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(position)
            chunk = handle.read()
            position = handle.tell()

        if chunk:
            print(chunk, end="" if chunk.endswith("\n") else "\n")

        remaining = deadline - time.monotonic()
        time.sleep(min(POLL_INTERVAL_SECONDS, max(remaining, 0)))

    print("\nStopped printing CLI logs (this script exits; the trading bot was not stopped).")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Start the same bot as start.py if needed, tail logs/cli.log briefly, then exit "
            "(bot keeps running). Orders and TP/SL follow the strategy; see logs/trading.log."
        ),
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=None,
        help=(
            "Seconds to tail logs/cli.log (default: system.run_bot_once_cli_follow_seconds in "
            "config.yaml). Bracket placement is logged in logs/trading.log when a signal fires."
        ),
    )
    return parser.parse_args()


def _follow_seconds_from_config(cli_seconds: float | None) -> float:
    if cli_seconds is not None:
        return float(cli_seconds)
    cfg = load_config()
    raw = cfg.get("system", {}).get("run_bot_once_cli_follow_seconds", DEFAULT_FOLLOW_SECONDS)
    return float(raw)


def main() -> int:
    args = parse_args()
    follow_seconds = _follow_seconds_from_config(args.seconds)
    if follow_seconds < 0:
        print("--seconds / config follow duration must be zero or greater", file=sys.stderr)
        return 2

    matches = find_bot_processes()
    started_pid: int | None = None
    if matches:
        print("Bot is already running. Reusing existing process.")
        print_bot_processes(matches)
    else:
        started_pid = start_bot_detached()
        print(f"No bot was running. Started detached bot process with PID: {started_pid}")

    follow_cli_log(follow_seconds)

    if matches:
        print("CLI follow finished. Trading bot continues in the background (existing process, see PID above).")
    else:
        print(f"CLI follow finished. Trading bot continues in the background (PID {started_pid}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
