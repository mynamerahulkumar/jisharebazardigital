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

ACTIVE_STATUSES = frozenset({"OPEN"})
COUNTABLE_STATUSES = frozenset({"OPEN", "CLOSED"})


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
        fixed = self.reconcile_stale_opens()
        if fixed > 0:
            print(
                f"Reconciled {fixed} stale OPEN row(s) in {self.path.name} "
                "(orphan entries excluded from daily limit)",
                file=__import__("sys").stderr,
            )

    def _ensure_file(self) -> None:
        if self.path.exists() and self.path.stat().st_size > 0:
            return
        with self.path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=TRADE_FIELDS)
            writer.writeheader()

    def _read_all_rows(self) -> list[dict[str, str]]:
        self._ensure_file()
        with self.path.open("r", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def _write_all_rows(self, rows: list[dict[str, str]]) -> None:
        with self.path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=TRADE_FIELDS)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in TRADE_FIELDS})

    def append(self, record: TradeRecord) -> None:
        with self.path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=TRADE_FIELDS)
            writer.writerow(asdict(record))

    def rows(self) -> Iterable[dict[str, str]]:
        yield from self._read_all_rows()

    def reconcile_stale_opens(self) -> int:
        """Pair legacy OPEN+CLOSED rows and mark duplicate unclosed OPEN rows as ORPHAN."""
        current_date = today_ist()
        rows = self._read_all_rows()
        if not rows:
            return 0

        today_entries = [
            (index, row)
            for index, row in enumerate(rows)
            if row.get("trade_date") == current_date and row.get("status") in ("OPEN", "CLOSED")
        ]
        today_entries.sort(key=lambda item: item[1].get("timestamp", ""))

        pending_open: dict[str, list[int]] = {}
        fixed = 0

        for index, row in today_entries:
            symbol = row.get("symbol", "")
            status = row.get("status", "")
            if status == "OPEN":
                pending_open.setdefault(symbol, []).append(index)
                continue
            if status == "CLOSED" and pending_open.get(symbol):
                pending_open[symbol].pop(0)

        for symbol, indices in pending_open.items():
            while len(indices) > 1:
                orphan_index = indices.pop(0)
                rows[orphan_index]["status"] = "ORPHAN"
                rows[orphan_index]["reason"] = "orphan_reconciled"
                rows[orphan_index]["exit_price"] = rows[orphan_index].get("exit_price") or "0"
                fixed += 1

        if fixed:
            self._write_all_rows(rows)
        return fixed

    def close_open_row(
        self,
        symbol: str,
        *,
        exit_price: float,
        realized_pnl: float,
        reason: str,
        paper_trading: bool,
        closed_at: str,
    ) -> None:
        """Update today's OPEN row for symbol to CLOSED; append only if no OPEN row exists (legacy logs)."""
        current_date = today_ist()
        rows = self._read_all_rows()
        open_index: int | None = None
        for index in range(len(rows) - 1, -1, -1):
            row = rows[index]
            if (
                row.get("trade_date") == current_date
                and row.get("symbol") == symbol
                and row.get("status") == "OPEN"
            ):
                open_index = index
                break

        if open_index is not None:
            row = rows[open_index]
            row["timestamp"] = closed_at
            row["exit_price"] = str(exit_price)
            row["realized_pnl"] = str(realized_pnl)
            row["status"] = "CLOSED"
            row["reason"] = reason
            row["paper_trading"] = str(paper_trading)
            self._write_all_rows(rows)
            return

        rows.append(
            {
                "timestamp": closed_at,
                "trade_date": current_date,
                "symbol": symbol,
                "side": "",
                "quantity": "0",
                "entry_price": "0",
                "exit_price": str(exit_price),
                "realized_pnl": str(realized_pnl),
                "status": "CLOSED",
                "reason": reason,
                "paper_trading": str(paper_trading),
            }
        )
        self._write_all_rows(rows)

    def entries_used_today(self) -> int:
        """Position entries used against max_trades_per_day (OPEN + CLOSED, excludes ORPHAN)."""
        current_date = today_ist()
        return sum(
            1
            for row in self.rows()
            if row.get("trade_date") == current_date and row.get("status") in COUNTABLE_STATUSES
        )

    def count_today(self) -> int:
        """Unclosed entries today (OPEN rows only)."""
        current_date = today_ist()
        return sum(
            1
            for row in self.rows()
            if row.get("trade_date") == current_date and row.get("status") in ACTIVE_STATUSES
        )

    def closed_count_today(self) -> int:
        current_date = today_ist()
        return sum(
            1
            for row in self.rows()
            if row.get("trade_date") == current_date and row.get("status") == "CLOSED"
        )

    def daily_realized_pnl(self, symbol: str | None = None) -> float:
        current_date = today_ist()
        total = 0.0
        for row in self.rows():
            if row.get("trade_date") != current_date:
                continue
            if row.get("status") not in COUNTABLE_STATUSES:
                continue
            if symbol is not None and row.get("symbol") != symbol:
                continue
            total += float(row.get("realized_pnl") or 0.0)
        return total
