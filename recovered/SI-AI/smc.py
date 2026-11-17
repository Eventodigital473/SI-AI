"""Compatibility shim for the retired legacy SMC module.

SI-AI is Binance USD-M USDT perpetual Futures only. This module deliberately
routes legacy entry points to the validated Futures engine; it never creates a
Binance Spot client.
"""
from __future__ import annotations

import SI_AI_smc as _engine

exchange = _engine.EXCHANGES["FUTURES"]
SYMBOLS = _engine.SYMBOLS
TIMEFRAMES = _engine.TIMEFRAMES
CANDLE_LIMIT = _engine.CANDLE_LIMIT


def get_candles(symbol, timeframe):
    return _engine.get_candles("FUTURES", symbol, timeframe)


def analyze(symbol, timeframe):
    return _engine.analyze("FUTURES", symbol, timeframe)


def run_analysis():
    return _engine.run_analysis()


def __getattr__(name):
    """Preserve access to shared SMC helpers through the Futures engine."""
    return getattr(_engine, name)
