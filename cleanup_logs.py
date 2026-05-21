from __future__ import annotations

from pathlib import Path

from utils.helpers import ROOT_DIR, load_config


def cleanup_logs() -> None:
    config = load_config()
    max_size_mb = float(config["system"].get("max_log_file_size_mb", 10))
    max_bytes = int(max_size_mb * 1024 * 1024)
    log_dir = ROOT_DIR / "logs"
    log_dir.mkdir(exist_ok=True)

    for path in log_dir.glob("*.log*"):
        if path.is_file() and path.stat().st_size > max_bytes:
            path.unlink()
            print(f"Deleted oversized log: {path}")


if __name__ == "__main__":
    cleanup_logs()
