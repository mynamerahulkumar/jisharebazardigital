from __future__ import annotations

"""
Bollinger reversal signals and how they appear in logs/trading.log (log_snapshot):

- LOWER_NEAR (buy.lower_band_touched): min(relevant lows) <= effective_lower + band_proximity_points
- UPPER_NEAR (sell.upper_band_touched): max(relevant highs) >= effective_upper - band_proximity_points
- PREV_HIGH_BREAK (buy.previous_high_broken): max(breakout highs) >= previous.high (configurable sources:
  completed bar, optional forming bar, optional live price). Same for sell with <= previous.low.
- BULLISH (buy): optional when require_bullish_candle_for_buy / signal_engine.candle_confirmation_enabled.
"""

from utils.helpers import Candle, IndicatorSnapshot, SignalDecision


def _fill_band_touch_meta(
    decision: SignalDecision,
    *,
    min_low: float,
    max_high: float,
    eff_lower: float,
    eff_upper: float,
    lower_threshold: float,
    upper_threshold: float,
    includes_forming: bool,
) -> None:
    decision.band_touch_min_low = min_low
    decision.band_touch_max_high = max_high
    decision.band_touch_lower_line = eff_lower
    decision.band_touch_upper_line = eff_upper
    decision.band_touch_lower_threshold = lower_threshold
    decision.band_touch_upper_threshold = upper_threshold
    decision.band_touch_includes_forming = includes_forming


def _require_bullish_for_buy(bb_config: dict, signal_engine: dict) -> bool:
    if "require_bullish_candle_for_buy" in bb_config:
        return bool(bb_config["require_bullish_candle_for_buy"])
    return bool(signal_engine.get("candle_confirmation_enabled", True))


def _require_bearish_for_sell(bb_config: dict, signal_engine: dict) -> bool:
    if "require_bearish_candle_for_sell" in bb_config:
        return bool(bb_config["require_bearish_candle_for_sell"])
    return bool(signal_engine.get("candle_confirmation_enabled", True))


class BollingerReversalStrategy:
    def __init__(self, config: dict) -> None:
        self.config = config

    def evaluate(
        self,
        candles: list[Candle],
        indicators: IndicatorSnapshot,
        forming: Candle | None = None,
        live_price: float | None = None,
    ) -> SignalDecision:
        if len(candles) < 2:
            return SignalDecision(status="WAITING_FOR_DATA", rejected_reason="not enough candles")

        current = candles[-1]
        previous = candles[-2]
        signal_control = self.config["signal_control"]
        rsi_config = self.config["rsi"]
        bb_config = self.config["bollinger_bands"]
        signal_engine = self.config.get("signal_engine", {})
        rsi_buy_level = float(rsi_config["rsi_buy_level"])
        rsi_sell_level = float(rsi_config["rsi_sell_level"])
        rsi_enabled = rsi_config.get("rsi_enabled", True)
        rsi_valid_for_buy = (not rsi_enabled) or (indicators.current_rsi <= rsi_sell_level)
        rsi_valid_for_sell = (not rsi_enabled) or (indicators.current_rsi >= rsi_buy_level)

        if not bb_config.get("bb_enabled", True):
            return SignalDecision(status="WAITING", rejected_reason="bollinger bands disabled")

        prox = float(bb_config.get("band_proximity_points", 0.0))
        offset_lo = float(bb_config.get("band_touch_offset_lower_points", 0.0))
        offset_up = float(bb_config.get("band_touch_offset_upper_points", 0.0))
        use_forming = bool(bb_config.get("band_touch_include_forming_candle", True))
        buy_bo_forming = bool(bb_config.get("buy_breakout_include_forming", True))
        sell_bo_forming = bool(bb_config.get("sell_breakout_include_forming", True))
        buy_bo_live = bool(bb_config.get("buy_breakout_use_live_price", False))
        sell_bo_live = bool(bb_config.get("sell_breakout_use_live_price", False))
        req_bull = _require_bullish_for_buy(bb_config, signal_engine)
        req_bear = _require_bearish_for_sell(bb_config, signal_engine)

        lows = [previous.low, current.low]
        highs = [previous.high, current.high]
        forming_used = False
        if forming is not None and use_forming:
            lows.append(forming.low)
            highs.append(forming.high)
            forming_used = True
        min_low = min(lows)
        max_high = max(highs)

        eff_lower = indicators.lower_band + offset_lo
        eff_upper = indicators.upper_band + offset_up
        lower_threshold = eff_lower + prox
        upper_threshold = eff_upper - prox
        upper_near = max_high >= upper_threshold
        lower_near = min_low <= lower_threshold

        buy_highs: list[float] = [current.high]
        if forming is not None and buy_bo_forming:
            buy_highs.append(forming.high)
        if buy_bo_live and live_price is not None and live_price > 0:
            buy_highs.append(float(live_price))
        breakout_buy_high = max(buy_highs)
        previous_high_broken = breakout_buy_high >= previous.high

        sell_lows: list[float] = [current.low]
        if forming is not None and sell_bo_forming:
            sell_lows.append(forming.low)
        if sell_bo_live and live_price is not None and live_price > 0:
            sell_lows.append(float(live_price))
        breakout_sell_low = min(sell_lows)
        previous_low_broken = breakout_sell_low <= previous.low

        bullish = current.close > current.open
        bearish = current.close < current.open

        sell = SignalDecision(
            action="sell",
            status="WAITING_FOR_SELL_CONFIRMATION",
            upper_band_touched=upper_near,
            bearish_candle=bearish,
            previous_low_broken=previous_low_broken,
            rsi_valid=rsi_valid_for_sell,
            confirmation_active=True,
        )
        buy = SignalDecision(
            action="buy",
            status="WAITING_FOR_BUY_CONFIRMATION",
            lower_band_touched=lower_near,
            bullish_candle=bullish,
            previous_high_broken=previous_high_broken,
            rsi_valid=rsi_valid_for_buy,
            confirmation_active=True,
        )
        touch_kw = dict(
            min_low=min_low,
            max_high=max_high,
            eff_lower=eff_lower,
            eff_upper=eff_upper,
            lower_threshold=lower_threshold,
            upper_threshold=upper_threshold,
            includes_forming=forming_used,
        )
        _fill_band_touch_meta(sell, **touch_kw)
        _fill_band_touch_meta(buy, **touch_kw)

        sell_body_ok = (not req_bear) or sell.bearish_candle
        buy_body_ok = (not req_bull) or buy.bullish_candle

        sell_ready = sell.upper_band_touched and sell_body_ok and sell.previous_low_broken and sell.rsi_valid
        buy_ready = buy.lower_band_touched and buy_body_ok and buy.previous_high_broken and buy.rsi_valid

        if sell_ready and signal_control.get("enable_sell_signals", True):
            sell.status = "SELL_CONFIRMED"
            return sell
        if buy_ready and signal_control.get("enable_buy_signals", True):
            buy.status = "BUY_CONFIRMED"
            return buy
        if sell.upper_band_touched:
            return self._reject(sell, req_bear=req_bear)
        if buy.lower_band_touched:
            return self._reject(buy, req_bull=req_bull)
        idle = "no band proximity" if (prox > 0 or offset_lo != 0.0 or offset_up != 0.0) else "no band touch"
        out = SignalDecision(status="WAITING", rejected_reason=idle)
        _fill_band_touch_meta(out, **touch_kw)
        return out

    def _reject(self, decision: SignalDecision, *, req_bull: bool = True, req_bear: bool = True) -> SignalDecision:
        missing: list[str] = []
        if decision.action == "sell":
            if req_bear and not decision.bearish_candle:
                missing.append("bearish candle not formed")
            if not decision.previous_low_broken:
                missing.append("previous candle low not reached (need min(low/live) <= prior low)")
        if decision.action == "buy":
            if req_bull and not decision.bullish_candle:
                missing.append("bullish candle not formed")
            if not decision.previous_high_broken:
                missing.append("previous candle high not reached (need max(high/live) >= prior high)")
        if not decision.rsi_valid:
            missing.append("RSI condition failed")
        decision.action = "hold"
        decision.status = "SIGNAL_REJECTED"
        decision.rejected_reason = ", ".join(missing) or "signal not confirmed"
        return decision
