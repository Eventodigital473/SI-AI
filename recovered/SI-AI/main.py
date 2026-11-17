import time
from flask import Flask, jsonify, request

import SI_AI_smc as smc

app = Flask(__name__)


def request_data():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else request.args


def validate_market_symbol(data):
    market = str(data.get("market", "FUTURES")).upper()
    symbol = str(data.get("symbol", "BTC/USDT")).upper()

    if market not in smc.MARKETS:
        raise ValueError("Unsupported market. SI-AI supports FUTURES only.")

    if symbol not in smc.get_symbols(market):
        smc.refresh_symbol_universe()
    if symbol not in smc.get_symbols(market):
        raise ValueError("Unsupported symbol for this market's selected USDT universe. Refresh /api/config.")

    return market, symbol


@app.route("/")
def home():
    return """
    <html>
    <head><title>SI AI</title></head>
    <body>
        <h1>SI AI</h1>
        <h2>Super Intelligent AI</h2>
        <p>SMC Market Intelligence Engine Connected.</p>
        <p>Public market data only. No automatic trading.</p>
        <ul>
            <li>/status</li>
            <li>/api/config</li>
            <li>/api/analyze</li>
            <li>/api/multi-timeframe</li>
        </ul>
    </body>
    </html>
    """


@app.route("/status")
def status():
    return jsonify({
        "name": "SI AI",
        "status": "Online",
        "version": "2.0",
        "smc_engine": "Connected",
        "trading_mode": "Analysis Only",
        "automatic_orders": False
    })


@app.route("/api/config")
def api_config():
    try:
        smc.refresh_symbol_universe()
    except Exception:
        # The endpoint can still report the last-known-good universe.
        pass
    return jsonify({
        "markets": smc.MARKETS,
        "symbols": smc.SYMBOLS,
        "symbols_by_market": {
            market: smc.get_symbols(market) for market in smc.MARKETS
        },
        "universe_status_by_market": {
            market: smc.MARKET_UNIVERSE_STATUS.get(market, "unknown")
            for market in smc.MARKETS
        },
        "risk_policy": {
            "reference_wallet_usdt": smc.PAPER_EQUITY_USDT,
            "margin_allocation_percent": smc.MARGIN_ALLOCATION_PERCENT,
            "margin_budget_usdt": smc.PAPER_EQUITY_USDT * smc.MARGIN_ALLOCATION_PERCENT / 100.0,
            "risk_per_trade_percent": smc.RISK_PER_TRADE_PERCENT,
            "recommended_futures_leverage": smc.RECOMMENDED_FUTURES_LEVERAGE,
            "leverage_status": "conservative_1x_only_until_liquidation_model_is_validated",
            "automatic_orders": False
        },
        "universe_policy": {
            "minimum_eligible_coins": smc.MIN_ELIGIBLE_COINS,
            "target_coins": smc.TARGET_UNIVERSE_SIZE,
            "maximum_coins": smc.MAX_UNIVERSE_SIZE,
            "refresh_seconds": smc.UNIVERSE_REFRESH_SECONDS,
            "futures_min_quote_volume_usdt": smc.MIN_FUTURES_QUOTE_VOLUME_USDT,
            "maximum_spread_percent": smc.MAX_SPREAD_PERCENT
        },
        "timeframes": smc.TIMEFRAMES,
        "default_market": "FUTURES",
        "default_symbol": "BTC/USDT",
        "default_timeframe": "1h"
    })


@app.route("/api/analyze", methods=["GET", "POST"])
def api_analyze():
    try:
        data = request_data()

        market, symbol = validate_market_symbol(data)
        timeframe = str(data.get("timeframe", "1h"))

        if timeframe not in smc.TIMEFRAMES:
            return jsonify({
                "error": "Unsupported timeframe",
                "available_timeframes": smc.TIMEFRAMES
            }), 400

        result = smc.analyze(market, symbol, timeframe)

        return jsonify({
            "success": True,
            "analysis_scope": "single_timeframe_only",
            "requires_multi_timeframe_confirmation": True,
            "analysis": result
        })

    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    except Exception as exc:
        return jsonify({
            "success": False,
            "error": type(exc).__name__,
            "message": str(exc)
        }), 502


@app.route("/api/multi-timeframe", methods=["GET", "POST"])
def api_multi_timeframe():
    try:
        data = request_data()
        market, symbol = validate_market_symbol(data)

        timeframes = data.get("timeframes", smc.TIMEFRAMES)

        if isinstance(timeframes, str):
            timeframes = [
                item.strip() for item in timeframes.split(",")
                if item.strip()
            ]

        if not isinstance(timeframes, list) or not timeframes:
            return jsonify({
                "success": False,
                "error": "Provide a non-empty timeframe list."
            }), 400

        if any(
            not isinstance(tf, str) or tf not in smc.TIMEFRAMES
            for tf in timeframes
        ):
            return jsonify({
                "success": False,
                "error": "Unsupported timeframe",
                "available_timeframes": smc.TIMEFRAMES
            }), 400

        if len(set(timeframes)) != len(timeframes):
            return jsonify({
                "success": False,
                "error": "Duplicate timeframes are not allowed."
            }), 400

        results = []
        errors = []

        for index, timeframe in enumerate(timeframes):
            try:
                result = smc.analyze(market, symbol, timeframe)
                results.append(result)

            except Exception as exc:
                errors.append({
                    "timeframe": timeframe,
                    "error": type(exc).__name__,
                    "message": str(exc)
                })

            if index < len(timeframes) - 1:
                time.sleep(smc.REQUEST_DELAY_SECONDS)

        if not results:
            return jsonify({
                "success": False,
                "message": "All timeframe analyses failed.",
                "errors": errors
            }), 502

        if errors:
            # Partial timeframe data must never produce an actionable confluence.
            combined = {
                "weighted_score": None,
                "overall_signal": "WAIT",
                "analysis_status": "INCOMPLETE",
                "reason": (
                    "One or more requested timeframe analyses failed; "
                    "incomplete confluence is not actionable."
                ),
            }
        else:
            combined = smc.combine_timeframes(results)
            combined["analysis_status"] = "COMPLETE"

        return jsonify({
            "success": True,
            "complete": not errors,
            "market": market,
            "symbol": symbol,
            "multi_timeframe": combined,
            "timeframe_count": len(results),
            "successful_analyses": results,
            "errors": errors,
            "automatic_orders": False
        })

    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    except Exception as exc:
        return jsonify({
            "success": False,
            "error": type(exc).__name__,
            "message": str(exc)
        }), 502


if __name__ == "__main__":
    print("====================================")
    print("       SI AI SYSTEM STARTING")
    print("====================================")
    print("SMC Engine: Connected")
    print("Market: Binance USD-M FUTURES only")
    print("Timeframes: 15m, 1h, 4h, 1d")
    print("Trading: Analysis Only")
    print("API: http://127.0.0.1:5000")
    print("====================================")

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )
