import time
from datetime import datetime, timezone
from flask import Flask, jsonify, request

import SI_AI_smc as smc
import si_ai_scanner as scanner
import signal_dashboard as dashboard_store

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


DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#101827">
<title>SI-AI Signal Dashboard</title>
<style>
:root{color-scheme:dark;font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#0b1220;color:#e7edf7}
*{box-sizing:border-box}body{margin:0;padding:18px;max-width:980px;margin-inline:auto}
header{padding:16px 0 20px;border-bottom:1px solid #293449}
h1{font-size:27px;margin:0 0 5px}h2{font-size:18px;margin:0 0 12px}
.muted{color:#9eabc0;font-size:13px}.safety{color:#a9c5db;font-size:13px;margin-top:10px}
.layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,2fr);gap:14px;margin-top:16px}
.panel{background:#131e30;border:1px solid #293449;border-radius:14px;padding:14px;min-width:0}
#signal-list{display:grid;gap:8px}.signal-item{width:100%;text-align:left;background:#1a2940;color:inherit;border:1px solid #35455e;border-radius:10px;padding:12px;cursor:pointer}
.signal-item strong{display:block;font-size:15px}.signal-item span{display:block;color:#aebbd0;font-size:12px;margin-top:4px}
.status{font-size:12px;font-weight:700;letter-spacing:.04em}.active{color:#58d68d}.invalid{color:#f0bd63}.stale{color:#ff9b83}
#side{font-size:28px;font-weight:800;margin:4px 0}.metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin:14px 0}
.metric{background:#1a2940;border-radius:9px;padding:10px;min-width:0}.metric small{display:block;color:#aebbd0;font-size:11px}.metric b{display:block;margin-top:4px;overflow-wrap:anywhere;font-size:15px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#0d1727;padding:12px;border-radius:9px;font-size:12px;line-height:1.5}
.empty{color:#aebbd0;padding:12px 2px;font-size:14px}
@media(max-width:680px){body{padding:12px}.layout{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>
</head>
<body>
<header>
<h1>SI-AI</h1>
<div class="muted">Binance USD-M Futures · Confirmed signal dashboard</div>
<div class="safety">Analysis only. No automatic orders. Review live price, exchange filters and risk before any manual trade.</div>
</header>
<div class="layout">
<section class="panel">
<h2>Recent signals</h2>
<div id="signal-list" class="empty">Loading saved signals…</div>
</section>
<section class="panel">
<div id="detail" class="empty">Select a signal to view its trade plan.</div>
</section>
</div>
<script>
"use strict";
const listNode=document.getElementById("signal-list");
const detailNode=document.getElementById("detail");
const requestedSymbol=(new URLSearchParams(location.search).get("symbol")||"").toUpperCase();
let currentItems=[];
function element(tag,className,text){const node=document.createElement(tag);if(className)node.className=className;if(text!==undefined)node.textContent=String(text);return node;}
function numberText(value,suffix=""){return typeof value==="number"&&Number.isFinite(value)?value.toLocaleString(undefined,{maximumFractionDigits:8})+suffix:"Unavailable";}
function showDetail(item){
 detailNode.replaceChildren();
 if(!item){detailNode.append(element("div","empty","No saved signal yet. The dashboard fills after the scanner confirms a signal and sends its alert."));return;}
 const heading=element("div","status "+(item.status==="ACTIVE"?(item.is_stale?"stale":"active"):"invalid"),item.status==="ACTIVE"?(item.is_stale?"STALE — CHECK LIVE DATA":"ACTIVE — CONFIRMED"):"WAIT — ENTRY NO LONGER CONFIRMED");
 detailNode.append(heading);
 detailNode.append(element("h2","",item.symbol+" · "+item.market));
 detailNode.append(element("div","",item.side||"WAIT"));
 const side=detailNode.lastChild;side.id="side";
 detailNode.append(element("div","muted","Last confirmed: "+(item.last_confirmed_at||"Unknown")));
 if(item.status==="ACTIVE"){
  const metrics=[
   ["Entry reference",numberText(item.entry_price)],
   ["Stop loss",numberText(item.stop_loss)],
   ["TP1 · 1R reference",numberText(item.entry_price!==null&&item.entry_price!==undefined&&item.stop_loss!==null?item.signal==="BUY"?item.entry_price+(item.entry_price-item.stop_loss):item.entry_price-(item.stop_loss-item.entry_price):null)],
   ["TP2 · 1.5R reference",numberText(item.entry_price!==null&&item.entry_price!==undefined&&item.stop_loss!==null?item.signal==="BUY"?item.entry_price+1.5*(item.entry_price-item.stop_loss):item.entry_price-1.5*(item.stop_loss-item.entry_price):null)],
   ["TP3 · engine target",numberText(item.take_profit)],
   ["Net reward / risk",numberText(item.reward_risk,":1")],
   ["Leverage guidance",numberText(item.leverage,"x")],
   ["Position size · paper",numberText(item.position_size," "+item.symbol.split("/")[0])],
   ["Notional · paper",numberText(item.notional_usdt," USDT")],
   ["Estimated margin",numberText(item.margin_usdt," USDT")],
   ["Estimated total risk",numberText(item.risk_usdt," USDT")],
   ["Estimated net target reward",numberText(item.estimated_net_reward_usdt," USDT")]
  ];
  const grid=element("div","metrics");
  for(const pair of metrics){const card=element("div","metric");card.append(element("small","",pair[0]),element("b","",pair[1]));grid.append(card);}
  detailNode.append(grid);
  if(item.is_stale)detailNode.append(element("p","status stale","This saved analysis is older than 2 hours. Do not use it as a fresh entry signal; wait for a new confirmed alert."));
 }else{
  detailNode.append(element("p","muted","The scanner withdrew the entry confirmation. Do not open a new position from this alert."));
 }
 detailNode.append(element("h2","","Reasons"));
 const reasons=Array.isArray(item.reasons)?item.reasons:[];
 detailNode.append(element("p","muted",reasons.length?reasons.join(" · "):"No reason details saved."));
 detailNode.append(element("h2","","Full alert"));
 detailNode.append(element("pre","",item.alert_text||"No alert text saved."));
}
function render(items){
 currentItems=items;
 listNode.replaceChildren();
 if(!items.length){listNode.className="empty";listNode.textContent="No saved confirmed signals yet. Keep the scanner running; signals appear here after confirmation.";showDetail(null);return;}
 listNode.className="";
 for(const item of items){
  const button=element("button","signal-item");
  button.type="button";
  button.append(element("strong","",(item.side||"WAIT")+" · "+item.symbol));
  button.append(element("span","",item.status==="ACTIVE"?(item.is_stale?"STALE":"ACTIVE"):"INVALIDATED"));
  button.append(element("span","",item.last_confirmed_at||"Timestamp unavailable"));
  button.addEventListener("click",()=>showDetail(item));
  listNode.append(button);
 }
 const selected=items.find(item=>item.symbol===requestedSymbol)||items[0];
 showDetail(selected);
}
async function refresh(){
 try{
  const response=await fetch("/api/latest-signals",{cache:"no-store"});
  const payload=await response.json();
  if(!response.ok||!payload.success)throw new Error(payload.error||"Dashboard data unavailable");
  render(payload.signals||[]);
 }catch(error){listNode.className="empty";listNode.textContent="Could not load signal data: "+error.message;}
}
refresh();
setInterval(refresh,15000);
</script>
</body>
</html>"""


@app.route("/")
def home():
    return DASHBOARD_HTML


@app.route("/signal")
def signal_dashboard():
    return DASHBOARD_HTML


@app.route("/api/latest-signals")
def api_latest_signals():
    try:
        records = dashboard_store.load_latest_signals()
    except RuntimeError as exc:
        return jsonify({"success": False, "error": str(exc)}), 503

    requested_symbol = str(request.args.get("symbol", "")).strip().upper()
    now = datetime.now(timezone.utc)
    signals = []
    for record in records.values():
        if requested_symbol and record.get("symbol", "").upper() != requested_symbol:
            continue
        item = dict(record)
        stamp = dashboard_store.parse_timestamp(item.get("last_confirmed_at"))
        age = (now - stamp).total_seconds() if stamp is not None else None
        item["age_seconds"] = max(0, int(age)) if age is not None else None
        item["is_stale"] = (
            age is None or age < -300
            or age > dashboard_store.STALE_AFTER_SECONDS
        )
        signals.append(item)

    signals.sort(
        key=lambda item: item.get("last_confirmed_at") or "",
        reverse=True,
    )
    response = jsonify({
        "success": True,
        "automatic_orders": False,
        "stale_after_seconds": dashboard_store.STALE_AFTER_SECONDS,
        "signals": signals,
    })
    response.headers["Cache-Control"] = "no-store"
    return response


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

        required_timeframes = list(smc.TIMEFRAMES)
        if (
            len(timeframes) != len(required_timeframes)
            or set(timeframes) != set(required_timeframes)
        ):
            return jsonify({
                "success": False,
                "error": (
                    "Actionable multi-timeframe analysis requires all production "
                    "timeframes: " + ", ".join(required_timeframes)
                ),
                "required_timeframes": required_timeframes,
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
            raw_signal = combined.get("overall_signal", "WAIT")
            result_by_timeframe = {
                result["timeframe"]: result for result in results
            }
            confirmed_signal = scanner.confirm_signal(
                market, result_by_timeframe, combined
            )
            combined["weighted_signal"] = raw_signal
            combined["overall_signal"] = confirmed_signal
            combined["confirmation_status"] = (
                "CONFIRMED" if confirmed_signal in ("BUY", "SELL") else "WAIT"
            )
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
