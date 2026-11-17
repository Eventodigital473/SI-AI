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



def test_futures_universe_accepts_raw_binance_bookticker_keyed_by_market_id(monkeypatch):
    class FakeFuturesExchange:
        markets = {
            "BTC/USDT:USDT": {
                "active": True,
                "quote": "USDT",
                "base": "BTC",
                "swap": True,
                "linear": True,
                "settle": "USDT",
                "symbol": "BTC/USDT:USDT",
                "id": "BTCUSDT",
            }
        }

        def load_markets(self):
            return self.markets

        def fetch_tickers(self):
            return {
                "BTC/USDT:USDT": {
                    "quoteVolume": 15_000_000.0,
                }
            }

        def fetch_bids_asks(self):
            return {
                "BTCUSDT": {
                    "info": {
                        "symbol": "BTCUSDT",
                        "bidPrice": "100.0",
                        "askPrice": "100.1",
                    }
                }
            }

    monkeypatch.setattr(smc, "MARKETS", ["FUTURES"])
    monkeypatch.setattr(smc, "EXCHANGES", {"FUTURES": FakeFuturesExchange()})
    monkeypatch.setattr(smc, "_MARKET_UNIVERSE_LAST_REFRESH", {"FUTURES": 0.0})
    monkeypatch.setattr(smc, "MARKET_SYMBOLS", {"FUTURES": []})
    monkeypatch.setattr(smc, "MARKET_UNIVERSE_STATUS", {"FUTURES": "not_refreshed"})
    monkeypatch.setattr(smc, "MARKET_UNIVERSE_DIAGNOSTICS", {"FUTURES": {}})
    monkeypatch.setattr(smc, "SYMBOLS", [])

    result = smc.refresh_symbol_universe(force=True)

    assert result["FUTURES"] == ["BTC/USDT"]
    assert smc.MARKET_UNIVERSE_DIAGNOSTICS["FUTURES"] == {
        "markets_seen": 1,
        "volume_qualified": 1,
        "book_ticker_matched": 1,
        "valid_bid_ask": 1,
        "spread_qualified": 1,
        "candidate_count": 1,
        "selected_count": 1,
    }
