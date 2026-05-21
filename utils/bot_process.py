"""Shared process detection for start.py / main.py bot instances (run_bot_once, status, stop)."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINTS = ("start.py", "main.py")
HELPER_SCRIPTS = frozenset({"run_bot_once.py", "status.py", "stop.py"})


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


def process_rows_with_elapsed() -> list[tuple[int, str, str]]:
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
    if token_names & HELPER_SCRIPTS:
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


def find_bot_processes_with_elapsed() -> list[tuple[int, str, str]]:
    current_pid = os.getpid()
    return [
        (pid, elapsed, command)
        for pid, elapsed, command in process_rows_with_elapsed()
        if pid != current_pid and references_this_bot(pid, command)
    ]
