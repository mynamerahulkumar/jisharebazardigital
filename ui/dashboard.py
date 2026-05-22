from __future__ import annotations

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from utils.helpers import BotMonitorSnapshot, ExchangePositionOverview, SymbolMonitorState


class Dashboard:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.console = Console()

    def start(self, symbols: list[str] | None = None) -> None:
        if self.enabled:
            sym_text = ", ".join(symbols) if symbols else "none"
            self.console.print(
                f"[bold blue]Dashboard started. Monitoring: {sym_text}[/bold blue]"
            )

    def stop(self) -> None:
        return

    def alert(self, message: str, style: str = "bold red") -> None:
        self.console.print(Panel(message, style=style))

    def update(self, snapshot: BotMonitorSnapshot) -> None:
        if not self.enabled:
            return
        renderable = Group(
            _header(snapshot),
            _symbols_table(snapshot),
            _pnl_summary_table(snapshot),
            _risk_exchange_table(snapshot),
        )
        self.console.rule(
            f"Signal Check | {snapshot.created_at} | {snapshot.timeframe} | "
            f"WS: {snapshot.websocket_status} | {len(snapshot.symbols)} symbol(s)"
        )
        self.console.print(renderable)


def _header(snapshot: BotMonitorSnapshot) -> Panel:
    text = Text()
    text.append(f"TIME (IST): {snapshot.created_at}\n", style="bold blue")
    text.append(f"TIMEFRAME: {snapshot.timeframe} | WEBSOCKET: {snapshot.websocket_status}\n")
    text.append(
        f"OVERALL P&L (bot): {_usd(snapshot.overall_pnl)} "
        f"(unreal {_usd(snapshot.total_unrealized_pnl)} | realized today {_usd(snapshot.total_realized_today)})"
    )
    return Panel(text, title="Delta BB + RSI Bot — Multi-Symbol")


def _symbols_table(snapshot: BotMonitorSnapshot) -> Table:
    table = Table(title="Symbols — Algo Stage & Breakout", expand=True)
    table.add_column("Symbol", style="cyan")
    table.add_column("TF", justify="center")
    table.add_column("Price", justify="right")
    table.add_column("Algo stage", style="magenta")
    table.add_column("Band", justify="center")
    table.add_column("Brk H", justify="center")
    table.add_column("Brk L", justify="center")
    table.add_column("RSI", justify="center")
    table.add_column("Position", justify="center")
    table.add_column("Unreal P&L", justify="right")
    table.add_column("Realized (today)", justify="right")
    table.add_column("Missing / note", overflow="fold")

    for state in snapshot.symbols:
        table.add_row(*_symbol_row_cells(state))

    return table


def _symbol_row_cells(state: SymbolMonitorState) -> tuple[str, ...]:
    signal = state.signal
    position = state.position
    return (
        state.symbol,
        state.timeframe,
        _num(state.current_price),
        _algo_stage(state),
        _band_zone(signal),
        _yes_short(signal.previous_high_broken),
        _yes_short(signal.previous_low_broken),
        _yes_short(signal.rsi_valid),
        _position_cell(position),
        _usd(position.unrealized_pnl) if position.active else "—",
        _usd(state.realized_pnl_today),
        signal.rejected_reason or ("READY" if signal.should_trade else "—"),
    )


def _algo_stage(state: SymbolMonitorState) -> str:
    signal = state.signal
    if signal.status == "POSITION_ACTIVE":
        return "POSITION_ACTIVE"
    hints: list[str] = []
    if signal.lower_band_touched:
        hints.append("near_lower")
    if signal.upper_band_touched:
        hints.append("near_upper")
    if signal.previous_high_broken:
        hints.append("high_break=YES")
    elif signal.confirmation_active:
        hints.append("high_break=NO")
    if signal.previous_low_broken:
        hints.append("low_break=YES")
    elif signal.confirmation_active:
        hints.append("low_break=NO")
    hint_str = f" ({', '.join(hints)})" if hints else ""
    return f"{signal.status}{hint_str}"


def _pnl_summary_table(snapshot: BotMonitorSnapshot) -> Table:
    table = Table(title="P&L Summary", expand=True)
    table.add_column("Metric", style="green")
    table.add_column("Value", justify="right")
    table.add_row("Total unrealized (open bot legs)", _usd(snapshot.total_unrealized_pnl))
    table.add_row("Sum realized today (per-symbol rows)", _usd(snapshot.total_realized_today))
    table.add_row("Daily realized (all symbols, CSV)", _usd(snapshot.daily_pnl))
    table.add_row("Overall P&L (daily realized + unrealized)", _usd(snapshot.overall_pnl))
    return table


def _risk_exchange_table(snapshot: BotMonitorSnapshot) -> Table:
    table = Table(title="Risk & Exchange", expand=True)
    table.add_column("Metric", style="green")
    table.add_column("Value")
    table.add_row("Entries used today (bot CSV)", _opens_today_cell(snapshot))
    table.add_row("Closes today (bot CSV)", str(snapshot.closed_trades_today))
    table.add_row(
        "CSV scope",
        "Only fills from this bot's OrderManager; manual Delta orders are not logged",
    )
    table.add_row(
        "Remaining (bot limit)",
        str(max(snapshot.max_trades_per_day - snapshot.trades_today, 0)),
    )
    table.add_row("Daily loss limit", _num(snapshot.daily_loss_limit))
    table.add_row("Uptime", f"{snapshot.running_seconds}s")
    table.add_row("Memory / CPU", f"{snapshot.memory_mb:.1f} MB / {snapshot.cpu_load_1m:.2f}")
    _add_exchange_rows(table, snapshot.exchange_positions)
    return table


def _opens_today_cell(snapshot: BotMonitorSnapshot) -> str:
    ex = snapshot.exchange_positions
    cell = (
        f"{snapshot.trades_today} / {snapshot.max_trades_per_day} "
        f"(entries today in logs/trades.csv; ORPHAN rows excluded)"
    )
    if ex.source == "ok":
        cell += f" — exchange {ex.open_count} open"
    return cell


def _position_cell(position) -> str:
    if position.active:
        return position.side.upper()
    return "flat"


def _band_zone(signal) -> str:
    if signal.upper_band_touched:
        return "NEAR U"
    if signal.lower_band_touched:
        return "NEAR L"
    return "OUT"


def _add_exchange_rows(table: Table, ex: ExchangePositionOverview) -> None:
    if ex.source == "off":
        table.add_row("Exchange positions", "fetch disabled (dashboard_exchange_positions)")
        return
    if ex.source == "paper":
        table.add_row("Exchange positions", "paper trading — not fetched")
        return
    if ex.source == "error":
        table.add_row("Exchange positions", f"error: {ex.error}")
        return
    table.add_row("Open on exchange (API)", str(ex.open_count))
    if ex.open_count == 0:
        table.add_row("Exchange PnL (open legs)", "n/a (no open positions)")
        return
    table.add_row("Sum realized PnL (exchange, USD)", _usd(ex.sum_realized_pnl))
    table.add_row("Est. unrealized USD (mark−entry)×contracts×cv)", _usd(ex.sum_est_unrealized))
    for line in ex.position_lines:
        table.add_row("— leg", line)


def _num(value: float) -> str:
    return f"{value:.2f}"


def _usd(value: float) -> str:
    magnitude = abs(value)
    if magnitude >= 1000:
        return f"{value:,.2f} USD"
    if magnitude >= 1:
        return f"{value:.2f} USD"
    return f"{value:.4f} USD"


def _yes_short(value: bool) -> str:
    return "YES" if value else "NO"
