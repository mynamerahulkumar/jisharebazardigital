from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from utils.helpers import ROOT_DIR
from utils.timezone_helper import today_ist

TRADE_FIELDS = [
    "timestamp",
    "trade_date",
    "symbol",
    "side",
    "quantity",
    "entry_price",
    "exit_price",
    "realized_pnl",
    "status",
    "reason",
    "paper_trading",
]


@dataclass(slots=True)
class TradeRecord:
    timestamp: str
    trade_date: str
    symbol: str
    side: str
    quantity: float
    entry_price: float
    exit_price: float
    realized_pnl: float
    status: str
    reason: str
    paper_trading: bool


class TradeTracker:
    def __init__(self, path: str | Path = "logs/trades.csv") -> None:
        self.path = Path(path)
        if not self.path.is_absolute():
            self.path = ROOT_DIR / self.path
        self.path.parent.mkdir(exist_ok=True)
        self._ensure_file()

    def _ensure_file(self) -> None:
        if self.path.exists() and self.path.stat().st_size > 0:
            return
        with self.path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=TRADE_FIELDS)
            writer.writeheader()

    def append(self, record: TradeRecord) -> None:
        with self.path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=TRADE_FIELDS)
            writer.writerow(asdict(record))

    def rows(self) -> Iterable[dict[str, str]]:
        self._ensure_file()
        with self.path.open("r", newline="", encoding="utf-8") as handle:
            yield from csv.DictReader(handle)

    def count_today(self) -> int:
        current_date = today_ist()
        return sum(1 for row in self.rows() if row.get("trade_date") == current_date and row.get("status") == "OPEN")

    def closed_count_today(self) -> int:
        current_date = today_ist()
        return sum(1 for row in self.rows() if row.get("trade_date") == current_date and row.get("status") == "CLOSED")

    def daily_realized_pnl(self, symbol: str | None = None) -> float:
        current_date = today_ist()
        total = 0.0
        for row in self.rows():
            if row.get("trade_date") != current_date:
                continue
            if symbol is not None and row.get("symbol") != symbol:
                continue
            total += float(row.get("realized_pnl") or 0.0)
        return total
