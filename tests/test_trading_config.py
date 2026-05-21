from __future__ import annotations

from utils.helpers import (
    active_trading_symbols,
    instrument_settings,
    normalize_trading_config,
    timeframe_summary,
)


def test_active_trading_symbols_from_instruments() -> None:
    config = {
        "trading": {
            "instruments": {
                "BTCUSD": {"enabled": True, "product_id": 27, "contract_value": 0.001},
                "ETHUSD": {"enabled": True, "product_id": 3136, "contract_value": 0.01},
                "XAUTUSD": {"enabled": False, "product_id": 131253, "contract_value": 0.001},
            }
        }
    }
    normalize_trading_config(config)
    assert active_trading_symbols(config) == ["BTCUSD", "ETHUSD"]
    assert config["trading"]["symbols"] == ["BTCUSD", "ETHUSD"]
    assert config["trading"]["product_ids"]["XAUTUSD"] == 131253
    assert config["trading"]["contract_value_by_symbol"]["ETHUSD"] == 0.01


def test_active_trading_symbols_fallback_to_symbols_list() -> None:
    config = {"trading": {"symbols": ["ETHUSD"], "product_ids": {"ETHUSD": 3136}}}
    assert active_trading_symbols(config) == ["ETHUSD"]


def test_instrument_settings_uses_per_symbol_overrides() -> None:
    config = {
        "trading": {
            "quantity": 10,
            "timeframe": "5m",
            "product_ids": {"BTCUSD": 27, "ETHUSD": 3136},
            "contract_value_by_symbol": {"BTCUSD": 0.001, "ETHUSD": 0.01},
            "instruments": {
                "BTCUSD": {
                    "enabled": True,
                    "product_id": 27,
                    "contract_value": 0.001,
                    "quantity": 10,
                    "timeframe": "5m",
                    "stop_loss_percent": 0.2,
                    "take_profit_percent": 0.4,
                },
                "ETHUSD": {
                    "enabled": True,
                    "product_id": 3136,
                    "contract_value": 0.01,
                    "quantity": 5,
                    "timeframe": "15m",
                    "stop_loss_percent": 0.25,
                    "take_profit_percent": 0.5,
                },
            },
        },
        "risk_management": {"stop_loss_percent": 0.2, "take_profit_percent": 0.4},
    }
    btc = instrument_settings(config, "BTCUSD")
    eth = instrument_settings(config, "ETHUSD")
    assert btc.quantity == 10
    assert btc.timeframe == "5m"
    assert btc.stop_loss_percent == 0.2
    assert eth.quantity == 5
    assert eth.timeframe == "15m"
    assert eth.stop_loss_percent == 0.25
    assert eth.take_profit_percent == 0.5


def test_instrument_settings_falls_back_to_globals() -> None:
    config = {
        "trading": {
            "quantity": 7,
            "timeframe": "1h",
            "product_ids": {"BTCUSD": 27},
            "contract_value_by_symbol": {"BTCUSD": 0.001},
            "instruments": {
                "BTCUSD": {"enabled": True, "product_id": 27, "contract_value": 0.001},
            },
        },
        "risk_management": {"stop_loss_percent": 0.3, "take_profit_percent": 0.6},
    }
    s = instrument_settings(config, "BTCUSD")
    assert s.quantity == 7
    assert s.timeframe == "1h"
    assert s.stop_loss_percent == 0.3
    assert s.take_profit_percent == 0.6


def test_timeframe_summary() -> None:
    config = {
        "trading": {
            "instruments": {
                "BTCUSD": {"enabled": True, "product_id": 27, "timeframe": "5m"},
                "ETHUSD": {"enabled": True, "product_id": 3136, "timeframe": "15m"},
            },
            "product_ids": {"BTCUSD": 27, "ETHUSD": 3136},
        },
        "risk_management": {},
    }
    normalize_trading_config(config)
    summary = timeframe_summary(config)
    assert "BTCUSD:5m" in summary
    assert "ETHUSD:15m" in summary
