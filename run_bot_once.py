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
import subprocess
import sys
import time
from pathlib import Path

from utils.bot_cli import format_trading_plan, resolve_trading_plan
from utils.bot_process import REPO_ROOT, find_bot_processes
from utils.helpers import load_config


LOG_DIR = REPO_ROOT / "logs"
CLI_LOG_PATH = LOG_DIR / "cli.log"
DEFAULT_FOLLOW_SECONDS = 30.0
POLL_INTERVAL_SECONDS = 0.25


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
    try:
        symbols, summary = resolve_trading_plan()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(format_trading_plan(symbols, summary))
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
