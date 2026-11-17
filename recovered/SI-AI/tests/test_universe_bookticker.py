import SI_AI_smc as smc
import pytest


def test_index_accepts_unified_and_raw_binance_aliases():
    unified = {
        "symbol": "BTC/USDT:USDT",
        "bid": 100.0,
        "ask": 100.1,
    }
    raw = {
        "symbol": "ETH/USDT:USDT",
        "info": {
            "symbol": "ETHUSDT",
            "bidPrice": "200.0",
            "askPrice": "200.2",
        },
    }
    indexed = smc._index_book_tickers({
        "BTC/USDT:USDT": unified,
        "ETHUSDT": raw,
    })

    assert indexed["BTC/USDT:USDT"] is unified
    assert indexed["ETHUSDT"] is raw
    assert indexed["ETH/USDT:USDT"] is raw


def test_find_book_ticker_resolves_exchange_symbol_and_market_id():
    quote = {"bid": 10.0, "ask": 10.01}
    indexed = smc._index_book_tickers({"ABCUSDT": quote})

    found = smc._find_book_ticker(
        indexed,
        "ABC/USDT:USDT",
        "ABC/USDT",
        {"symbol": "ABC/USDT:USDT", "id": "ABCUSDT"},
    )

    assert found is quote


def test_book_ticker_prices_accept_normalized_ccxt_fields():
    assert smc._book_ticker_prices({"bid": 99.0, "ask": 101.0}) == (99.0, 101.0)


def test_book_ticker_prices_accept_raw_binance_info_fields():
    assert smc._book_ticker_prices({
        "info": {"bidPrice": "99.0", "askPrice": "101.0"}
    }) == (99.0, 101.0)


def test_spread_percent_uses_midpoint_relative_algebra():
    # 100 * (101 - 99) / ((101 + 99) / 2) = 2.0 percent.
    assert smc._spread_percent(99.0, 101.0) == 2.0
    assert smc._spread_percent(100.0, 100.1) == pytest.approx(100.0 * 0.1 / 100.05, rel=1e-12, abs=1e-12)


def test_spread_percent_rejects_invalid_quotes():
    assert smc._spread_percent(None, 101.0) is None
    assert smc._spread_percent(0.0, 101.0) is None
    assert smc._spread_percent(102.0, 101.0) is None



def test_fee_free_long_reward_risk_matches_algebra():
    result = smc.calculate_net_reward_risk(
        100.0, 95.0, 110.0, "LONG", "FUTURES",
        fee_rate=0.0, slippage_rate=0.0,
    )
    assert result == 2.0


def test_fee_free_short_reward_risk_matches_algebra():
    result = smc.calculate_net_reward_risk(
        100.0, 105.0, 90.0, "SHORT", "FUTURES",
        fee_rate=0.0, slippage_rate=0.0,
    )
    assert result == 2.0


def test_transaction_costs_reduce_net_reward_risk():
    gross = smc.calculate_net_reward_risk(
        100.0, 95.0, 110.0, "LONG", "FUTURES",
        fee_rate=0.0, slippage_rate=0.0,
    )
    net = smc.calculate_net_reward_risk(
        100.0, 95.0, 110.0, "LONG", "FUTURES",
        fee_rate=0.0005, slippage_rate=0.0002,
    )
    assert net < gross
