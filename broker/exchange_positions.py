from __future__ import annotations

from typing import Any

from utils.helpers import ExchangePositionOverview


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def open_position_product_ids(raw: Any) -> set[int]:
    """Product ids with non-zero size from /v2/positions/margined result."""
    if raw is None:
        return set()
    rows: list[dict[str, Any]]
    if isinstance(raw, list):
        rows = [r for r in raw if isinstance(r, dict)]
    elif isinstance(raw, dict):
        rows = [raw]
    else:
        return set()
    out: set[int] = set()
    for item in rows:
        if _to_int(item.get("size")) == 0:
            continue
        out.add(_to_int(item.get("product_id")))
    return out


def margined_positions_to_overview(
    raw: Any,
    price_by_symbol: dict[str, float],
    *,
    product_id_to_symbol: dict[int, str] | None = None,
    product_id_to_contract_value: dict[int, float] | None = None,
) -> ExchangePositionOverview:
    """Parse Delta /v2/positions/margined result into a dashboard-friendly overview."""
    if raw is None:
        return ExchangePositionOverview(source="ok")
    rows: list[dict[str, Any]]
    if isinstance(raw, list):
        rows = [r for r in raw if isinstance(r, dict)]
    elif isinstance(raw, dict):
        rows = [raw]
    else:
        return ExchangePositionOverview(source="error", error="unexpected positions response type")

    lines: list[str] = []
    open_count = 0
    sum_realized = 0.0
    sum_unreal = 0.0

    for item in rows:
        size = _to_int(item.get("size"))
        if size == 0:
            continue
        open_count += 1
        api_symbol = str(item.get("product_symbol") or item.get("symbol") or "")
        pid = _to_int(item.get("product_id"))
        config_symbol = product_id_to_symbol.get(pid, "") if product_id_to_symbol else ""
        label = api_symbol or (config_symbol or f"id:{pid}")
        entry = _to_float(item.get("entry_price"))
        realized = _to_float(item.get("realized_pnl"))
        sum_realized += realized
        side = "long" if size > 0 else "short"
        qty = abs(size)
        mark = 0.0
        if config_symbol:
            mark = price_by_symbol.get(config_symbol, 0.0)
        if not mark and api_symbol:
            mark = price_by_symbol.get(api_symbol, 0.0)
        cv = 1.0
        if product_id_to_contract_value and pid in product_id_to_contract_value:
            cv = float(product_id_to_contract_value[pid])
        if mark <= 0:
            est = 0.0
        elif size > 0:
            est = (mark - entry) * qty * cv
        else:
            est = (entry - mark) * qty * cv
        sum_unreal += est
        lines.append(f"{label} {side} qty={qty} entry={entry:.2f} realized={realized:.4f} USD")

    return ExchangePositionOverview(
        source="ok",
        open_count=open_count,
        position_lines=tuple(lines[:8]),
        sum_realized_pnl=sum_realized,
        sum_est_unrealized=sum_unreal,
    )
