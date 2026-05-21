Create a lightweight, production-ready Python algorithmic trading bot for Delta Exchange API using Bollinger Band + RSI reversal confirmation strategy.

IMPORTANT SYSTEM GOALS:
- LOW AWS COST
- LOW CPU usage
- LOW RAM usage
- Cloud-safe
- Local machine friendly
- Websocket-first architecture
- Fast startup
- Auto stop on critical failures
- Minimal API calls
- Everything configurable

Use:
- Python 3.11+
- UV package manager
- Asyncio
- Lightweight dependencies only

Startup Command:
uv run start.py

OR

python start.py

Reference Files:
- bkp/python-rest-client-master/delta_rest_client/delta_rest_client.py
- bkp/code_template_delta.md

Official Delta Docs:
- https://docs.delta.exchange/#introduction

Exchange Products:
- BTCUSD → product_id: 27
- ETHUSD → product_id: 3136

━━━━━━━━━━━━━━━━━━━━━━
STRATEGY
━━━━━━━━━━━━━━━━━━━━━━

Strategy Name:
Bollinger Band Reversal Confirmation Strategy

SELL LOGIC:
1. Price touches/crosses Upper Bollinger Band
2. Candle starts moving downward
3. Next candle closes BELOW previous candle LOW
4. RSI confirmation passes
5. Execute SELL order

BUY LOGIC:
1. Price touches/crosses Lower Bollinger Band
2. Candle starts moving upward
3. Next candle closes ABOVE previous candle HIGH
4. RSI confirmation passes
5. Execute BUY order

━━━━━━━━━━━━━━━━━━━━━━
VERY IMPORTANT TRADING RULES
━━━━━━━━━━━━━━━━━━━━━━

1. ONLY ONE ACTIVE POSITION AT A TIME
- If one position is active:
  - Do NOT take another trade
  - Ignore all new signals
  - Continue monitoring current position

2. NEW POSITION ONLY AFTER:
- TP hit
- SL hit
- Manual close
- Position closed completely

3. MAX TRADES PER DAY
- Must be configurable
- Example:
  max_trades_per_day: 5

4. TRADE COUNT TRACKING
- Save every executed trade into file/database
- Calculate total trades using IST timezone
- Persist trade count even after restart

5. DAILY LIMIT LOGIC
IF max trades reached:
- Print warning in CLI
- Save log
- Gracefully stop program
- Exit process completely to save AWS cost

Example:
🛑 DAILY TRADE LIMIT REACHED
Total trades today: 5
Bot shutting down safely...

6. API ERROR HANDLING
If critical error occurs:
- Invalid API key
- Authentication failure
- Insufficient balance
- Invalid permissions
- Permanent websocket failure

THEN:
- Log error clearly
- Show error in terminal
- Gracefully stop bot
- Exit process immediately

Reason:
Reduce cloud cost and prevent useless execution.

━━━━━━━━━━━━━━━━━━━━━━
SIGNAL DETECTION ENGINE
━━━━━━━━━━━━━━━━━━━━━━

VERY IMPORTANT:
- Every 30 seconds:
  - Check signals
  - Update dashboard
  - Validate position status
  - Validate TP/SL
  - Monitor websocket health

This interval MUST be configurable:
signal_check_interval_seconds: 30

Use efficient async sleep:
await asyncio.sleep()

Avoid high CPU loops.

━━━━━━━━━━━━━━━━━━━━━━
TIMEZONE REQUIREMENT
━━━━━━━━━━━━━━━━━━━━━━

ALL TIME MUST USE:
Asia/Kolkata (IST)

Examples:
- Trade timestamps
- Daily trade count
- Logs
- Session time
- Dashboard clock

Use:
zoneinfo or pytz

━━━━━━━━━━━━━━━━━━━━━━
CONFIGURATION FILE
━━━━━━━━━━━━━━━━━━━━━━

ALL values MUST come from:
config/config.yaml

Configurable Parameters:

Exchange:
- api_key
- api_secret
- base_url

Trading:
- symbols
- product_ids
- timeframe
- leverage
- quantity
- order_type
- paper_trading

Signal Engine:
- signal_check_interval_seconds
- candle_confirmation_enabled
- breakout_confirmation_candles
- cooldown_seconds

Bollinger Bands:
- bb_enabled
- bb_length
- bb_std_dev
- bb_source

RSI:
- rsi_enabled
- rsi_length
- rsi_buy_level
- rsi_sell_level

Signal Control:
- enable_buy_signals
- enable_sell_signals

Risk Management:
- stop_loss
- take_profit
- trailing_stop
- break_even_enabled
- max_trades_per_day
- max_open_positions
- daily_loss_limit

Session:
- trading_start_time
- trading_end_time
- square_off_time

System:
- websocket_enabled
- colored_console
- log_to_file
- log_rotation_enabled
- max_log_file_size_mb
- retry_count
- retry_delay

━━━━━━━━━━━━━━━━━━━━━━
LOGGING SYSTEM
━━━━━━━━━━━━━━━━━━━━━━

IMPORTANT:
Save ALL logs to file.

Required Logs:
- logs/trading.log
- logs/error.log
- logs/trades.csv
- logs/system.log

Log Requirements:
- Timestamp in IST
- Signal detections
- Position status
- TP/SL events
- Trade entries
- Trade exits
- Errors
- Websocket reconnects
- Daily trade count

LOG ROTATION:
If log file exceeds configured size:
Example:
max_log_file_size_mb: 10

Then:
- Rotate logs automatically
OR
- Support cleanup script

Generate:
cleanup_logs.py

cleanup_logs.py should:
- Delete logs above configured size
- Keep latest logs
- Be lightweight

━━━━━━━━━━━━━━━━━━━━━━
CLI DASHBOARD
━━━━━━━━━━━━━━━━━━━━━━

Create CLEAR colorful terminal dashboard.

Dashboard Example:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TIME (IST): 2026-05-07 22:15:20

SYMBOL: BTCUSD
TIMEFRAME: 1H

PRICE: 94500

BOLLINGER BANDS:
UPPER: 94800
MIDDLE: 94200
LOWER: 93600

RSI: 72

SIGNAL STATUS:
🟡 WAITING FOR CONFIRMATION

POSITION STATUS:
✅ ACTIVE SHORT POSITION

ENTRY PRICE: 94450
CURRENT PnL: +1250

SL: 94700
TP: 93800

TRADES TODAY: 3 / 5

WEBSOCKET: CONNECTED
API STATUS: HEALTHY

NEXT SIGNAL CHECK: 30 sec
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Colors:
- Green → Profit / BUY
- Red → SELL / Loss
- Yellow → Waiting
- Blue → Info
- Magenta → Signals

CLI Requirements:
- Clear readable output
- Minimal flickering
- Lightweight rendering
- Real-time updates
- Error alerts
- Trade alerts
- Reconnection alerts

━━━━━━━━━━━━━━━━━━━━━━
PERFORMANCE REQUIREMENTS
━━━━━━━━━━━━━━━━━━━━━━

VERY IMPORTANT:
- Optimize for cheap AWS VM
- Must run on:
  - t2.micro
  - t3.micro
  - 1 CPU VPS
  - 1GB RAM

Avoid:
- Heavy frameworks
- Unnecessary threads
- High-frequency polling
- Memory-heavy libraries

Prefer:
- Asyncio
- Websocket streams
- Lightweight architecture

━━━━━━━━━━━━━━━━━━━━━━
PROJECT STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━

project/
│
├── start.py
├── cleanup_logs.py
├── main.py
├── pyproject.toml
├── requirements.txt
├── .python-version
├── .env.example
├── config/
│   └── config.yaml
├── strategy/
│   ├── bollinger_strategy.py
│   ├── signal_generator.py
│   ├── indicator_engine.py
│   └── risk_manager.py
├── broker/
│   ├── delta_client.py
│   ├── websocket_client.py
│   └── order_manager.py
├── ui/
│   └── dashboard.py
├── utils/
│   ├── logger.py
│   ├── trade_tracker.py
│   ├── timezone_helper.py
│   └── helpers.py
├── logs/
└── README.md

━━━━━━━━━━━━━━━━━━━━━━
DEPENDENCIES
━━━━━━━━━━━━━━━━━━━━━━

Use ONLY lightweight dependencies:
- aiohttp
- websockets
- rich
- pyyaml
- python-dotenv

Avoid heavy dependencies unless necessary.

Generate:
1. Complete Python source code
2. Lightweight architecture
3. pyproject.toml
4. requirements.txt
5. UV setup instructions
6. config.yaml example
7. cleanup_logs.py
8. README.md
9. AWS deployment guide
10. Local setup guide
11. Rich colorful dashboard
12. Trade tracking system
13. IST timezone support

Coding Standards:
- Type hints
- Proper comments
- Modular architecture
- Lightweight OOP
- Fast startup
- Graceful shutdown
- Minimal CPU usage

IMPORTANT FINAL REQUIREMENTS:
- EVERYTHING configurable
- STOP bot on critical errors
- STOP bot after daily trade limit
- ONLY ONE position at a time
- SAVE trade history persistently
- USE IST timezone everywhere
- LOW cloud cost optimized
- Local-first development
- Cloud-safe production architecture