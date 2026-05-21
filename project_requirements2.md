━━━━━━━━━━━━━━━━━━━━━━
ADVANCED LIVE MONITORING
━━━━━━━━━━━━━━━━━━━━━━

VERY IMPORTANT:
CLI dashboard and logs must continuously show ALL important current and previous values for debugging and signal validation.

Display Current Candle Values:
- Current Open
- Current High
- Current Low
- Current Close
- Current Candle Direction

Display Previous Candle Values:
- Previous Open
- Previous High
- Previous Low
- Previous Close

Display Bollinger Band Values:
- Upper Band
- Middle Band
- Lower Band

Display Distance Metrics:
- Distance from Upper Band
- Distance from Lower Band
- Distance from Middle Band

Display RSI Information:
- Current RSI
- Previous RSI
- RSI Trend Direction

Display Signal Information:
- Current Signal State
- Waiting for BUY
- Waiting for SELL
- Waiting for Confirmation
- Confirmation Candle Active
- Signal Rejected Reason

Display Confirmation Logic:
SELL Example:
- Upper band touched: YES/NO
- Bearish candle formed: YES/NO
- Previous candle low broken: YES/NO
- RSI condition passed: YES/NO

BUY Example:
- Lower band touched: YES/NO
- Bullish candle formed: YES/NO
- Previous candle high broken: YES/NO
- RSI condition passed: YES/NO

Display Position Information:
- Current Position Status
- Entry Price
- Current Quantity
- Current PnL
- Realized PnL
- Unrealized PnL
- Stop Loss
- Take Profit
- Trailing Stop Status

Display Daily Information:
- Total Trades Today
- Remaining Trades Today
- Daily PnL
- Daily Loss Limit Status

Display System Information:
- API Status
- Websocket Status
- Last Signal Check Time
- Next Signal Check Time
- Memory Usage
- CPU Usage
- Bot Running Time

━━━━━━━━━━━━━━━━━━━━━━
LOGGING REQUIREMENTS
━━━━━━━━━━━━━━━━━━━━━━

Save ALL important values into logs.

Every signal check cycle (30 sec):
- Save indicator values
- Save candle values
- Save signal state
- Save rejection reason
- Save position state

Example Logs:
[INFO] BTCUSD | PRICE=94500 | RSI=72 | BB_UPPER=94800 | BB_MIDDLE=94200 | BB_LOWER=93600

[INFO] SELL SIGNAL WAITING | Upper band touched | Waiting for previous candle low breakdown

[INFO] CONFIRMATION PASSED | SELL EXECUTED

[INFO] ACTIVE POSITION | ENTRY=94450 | PNL=+1200

[INFO] SIGNAL REJECTED | RSI condition failed

━━━━━━━━━━━━━━━━━━━━━━
CLI DASHBOARD EXAMPLE
━━━━━━━━━━━━━━━━━━━━━━

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TIME (IST): 2026-05-07 22:15:20

SYMBOL: BTCUSD
TIMEFRAME: 1H

CURRENT CANDLE:
OPEN: 94400
HIGH: 94650
LOW: 94350
CLOSE: 94500

PREVIOUS CANDLE:
HIGH: 94720
LOW: 94220

BOLLINGER BANDS:
UPPER: 94800
MIDDLE: 94200
LOWER: 93600

DISTANCE:
TO UPPER: 300
TO LOWER: 900

RSI:
CURRENT RSI: 72
PREVIOUS RSI: 75

SIGNAL STATUS:
🟡 WAITING FOR SELL CONFIRMATION

SELL CONDITIONS:
Upper Band Touch: ✅
Bearish Candle: ✅
Previous Low Break: ❌
RSI Valid: ✅

POSITION:
NO ACTIVE POSITION

TRADES TODAY:
3 / 5

WEBSOCKET:
CONNECTED

API:
HEALTHY

NEXT CHECK:
30 sec
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

IMPORTANT:
- Make CLI extremely readable
- Make debugging easy
- Show WHY signal was accepted/rejected
- Save all important values into logs
- Keep rendering lightweight
- Avoid high CPU usage
- Keep terminal updates efficient