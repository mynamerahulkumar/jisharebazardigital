from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO

from main import main


REPO_ROOT = Path(__file__).resolve().parent
CLI_LOG_PATH = REPO_ROOT / "logs" / "cli.log"


class TeeStream:
    def __init__(self, terminal: TextIO, log_file: TextIO) -> None:
        self.terminal = terminal
        self.log_file = log_file

    def write(self, text: str) -> int:
        self.terminal.write(text)
        self.log_file.write(text)
        self.log_file.flush()
        return len(text)

    def flush(self) -> None:
        self.terminal.flush()
        self.log_file.flush()

    def isatty(self) -> bool:
        return self.terminal.isatty()

    @property
    def encoding(self) -> str | None:
        return self.terminal.encoding

    def __getattr__(self, name: str) -> object:
        return getattr(self.terminal, name)


@contextmanager
def tee_cli_output() -> object:
    CLI_LOG_PATH.parent.mkdir(exist_ok=True)
    with CLI_LOG_PATH.open("a", encoding="utf-8") as log_file:
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        sys.stdout = TeeStream(original_stdout, log_file)  # type: ignore[assignment]
        sys.stderr = TeeStream(original_stderr, log_file)  # type: ignore[assignment]
        try:
            yield
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr


if __name__ == "__main__":
    with tee_cli_output():
        raise SystemExit(main())
