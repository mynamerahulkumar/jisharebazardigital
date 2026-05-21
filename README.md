# Delta BB + RSI Trading Bot

Lightweight Python 3.11 trading bot for Delta Exchange using a Bollinger Band reversal setup with RSI and candle confirmation.

The default configuration is cloud-safe and local-friendly:

- Paper trading is enabled by default.
- Multiple symbols can trade concurrently when enabled in `trading.instruments` (up to `max_open_positions`).
- Daily trade and daily loss limits stop the bot completely.
- Signal checks use configurable async sleeps to avoid high CPU usage.
- Timestamps, logs, trade counts, and dashboard clock use Asia/Kolkata.

## Setup With UV

```bash
uv sync
cp .env.example .env
uv run start.py
```

## Setup With Python

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python start.py
```

## Configuration

Edit `config/config.yaml`. Important defaults:

- `trading.paper_trading: true`
- `exchange.base_url: https://cdn-ind.testnet.deltaex.org`
- `trading.instruments` — per-symbol `enabled`, `product_id`, `contract_value`, `quantity`, `timeframe`, `stop_loss_percent`, `take_profit_percent` (see `bkp/PRODUCT_ID_DETAILS.md`). Omitted fields fall back to global `trading.quantity`, `trading.timeframe`, and `risk_management` TP/SL percents.
- Enabled symbols run in parallel; the CLI shows each symbol’s timeframe, algo stage, breakout flags, and P&L plus overall P&L in one snapshot
- `risk_management.stop_loss_percent: 0.35`
- `risk_management.take_profit_percent: 0.75`
- `risk_management.max_trades_per_day: 5`
- `signal_engine.signal_check_interval_seconds: 30`

For live trading, set `DELTA_API_KEY` and `DELTA_API_SECRET` in `.env`, choose the correct Delta `base_url` and `websocket_url`, then set `paper_trading: false`.

Risk distances are configured as percentages of entry price. For example, a BUY entry at `95000` with `stop_loss_percent: 0.35` sets SL near `94667.50`, and `take_profit_percent: 0.75` sets TP near `95712.50`. If trailing stop is enabled, `trailing_stop.trail_percent` trails from the best favorable price.

## Strategy

Sell confirmation:

1. Price touches or crosses the upper Bollinger Band.
2. A bearish candle forms.
3. The confirmation candle closes below the previous candle low.
4. RSI is between the configured buy and sell levels.

Buy confirmation:

1. Price touches or crosses the lower Bollinger Band.
2. A bullish candle forms.
3. The confirmation candle closes above the previous candle high.
4. RSI is between the configured buy and sell levels.

## Logs

Generated under `logs/`:

- `trading.log`: signal checks, indicators, candles, positions, daily status.
- `error.log`: critical and unexpected errors.
- `system.log`: startup, shutdown, websocket reconnects.
- `trades.csv`: persistent trade entries and exits.

Run log cleanup manually:

```bash
python cleanup_logs.py
```

## AWS Deployment Notes

Use a small instance such as `t3.micro` or a 1 GB VPS. Keep `paper_trading: true` until you verify API credentials, symbol/product IDs, and the dashboard output.

Suggested production run command:

```bash
uv run start.py
```

Use a process manager such as `systemd` only after confirming the bot exits correctly on critical failures. The bot intentionally exits on invalid credentials, insufficient balance, websocket permanent failure, daily trade limit, or daily loss limit to avoid wasted cloud cost.

## Verification

```bash
python -m compileall .
```

The bot may make public REST calls for candle backfill at startup. Websocket is preferred once market data is flowing.
