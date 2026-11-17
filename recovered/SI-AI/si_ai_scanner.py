import argparse
import fcntl
import json
import logging
import math
import os
import subprocess
import shutil
import sys
import tempfile
import time
from pathlib import Path

import SI_AI_smc as smc


BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "si_ai_scanner_state.json"
LOCK_FILE = BASE_DIR / "si_ai_scanner.lock"
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "si_ai_scanner.log"

EXPECTED_MARKETS = {"FUTURES"}
EXPECTED_TIMEFRAMES = ["15m", "1h", "4h", "1d"]
STATE_VERSION = 2
SIGNAL_REPEAT_ALERT_SECONDS = 6 * 60 * 60

logger = logging.getLogger("SI_AI_SCANNER")


def validate_config():
    if set(smc.MARKETS) != EXPECTED_MARKETS:
        raise RuntimeError("Unexpected MARKETS configuration")

    if list(smc.TIMEFRAMES) != EXPECTED_TIMEFRAMES:
        raise RuntimeError("Unexpected TIMEFRAMES configuration")

    for name in ("get_candles", "analyze_candles", "combine_timeframes",
                 "refresh_symbol_universe", "get_symbols",
                 "validate_candle_freshness"):
        if not callable(getattr(smc, name, None)):
            raise RuntimeError(f"Required engine function missing: {name}")

    minimum_rr = float(smc.MIN_REWARD_RISK)
    if not math.isfinite(minimum_rr) or minimum_rr < 2.0:
        raise RuntimeError("Minimum reward/risk must be at least 2.0")

    minimum_coins = int(smc.MIN_ELIGIBLE_COINS)
    maximum_coins = int(smc.MAX_UNIVERSE_SIZE)
    target_coins = int(smc.TARGET_UNIVERSE_SIZE)
    if minimum_coins < 15 or maximum_coins < minimum_coins:
        raise RuntimeError("Dynamic coin-universe limits are invalid")
    if not minimum_coins <= target_coins <= maximum_coins:
        raise RuntimeError("Target coin count must be between minimum and maximum")

    risk_percent = number(getattr(smc, "RISK_PER_TRADE_PERCENT", None))
    margin_percent = number(getattr(smc, "MARGIN_ALLOCATION_PERCENT", None))
    leverage = number(getattr(smc, "RECOMMENDED_FUTURES_LEVERAGE", None))
    if risk_percent is None or not math.isclose(risk_percent, 0.5, abs_tol=1e-9):
        raise RuntimeError("Per-trade risk policy must remain at 0.5%")
    if margin_percent is None or not math.isclose(margin_percent, 20.0, abs_tol=1e-9):
        raise RuntimeError("Margin allocation cap must remain at 20%")
    if leverage is None or not math.isclose(leverage, 1.0, abs_tol=1e-9):
        raise RuntimeError("Futures leverage must remain at conservative 1x")


def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


def acquire_lock():
    handle = open(LOCK_FILE, "a", encoding="utf-8")

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise RuntimeError("Another SI-AI scanner is already running")

    return handle


def load_state():
    if not STATE_FILE.exists():
        return {"version": STATE_VERSION, "last_signals": {}}

    try:
        with STATE_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:
        raise RuntimeError(
            f"State file is unreadable; preserving it: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise RuntimeError("Invalid state file: expected JSON object")

    version = data.get("version")
    if version not in (1, STATE_VERSION):
        raise RuntimeError("Unsupported state file version")

    signals = data.get("last_signals")
    if not isinstance(signals, dict):
        raise RuntimeError("Invalid state file: last_signals must be an object")

    # Migrate the old signal-only state safely. The previous notification time
    # is unknown, so an existing actionable signal may be refreshed once.
    if version == 1:
        data = {
            "version": STATE_VERSION,
            "last_signals": signals,
            "last_notified_at": {},
        }

    notified_at = data.get("last_notified_at")
    if not isinstance(notified_at, dict):
        raise RuntimeError("Invalid state file: last_notified_at must be an object")

    for key, value in signals.items():
        parts = key.split("|", 1)
        if (
            len(parts) != 2
            or parts[0] not in EXPECTED_MARKETS
            or not parts[1].endswith("/USDT")
            or parts[1].count("/") != 1
        ):
            raise RuntimeError(f"Invalid saved state key: {key}")
        if value not in ("BUY", "SELL", "WAIT"):
            raise RuntimeError(f"Invalid saved signal for {key}")

    for key, value in notified_at.items():
        if key not in signals:
            raise RuntimeError(f"Notification timestamp has no saved signal: {key}")
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or value < 0
        ):
            raise RuntimeError(f"Invalid notification timestamp for {key}")

    return data


def should_suppress_duplicate(signal, previous, last_notified_at, now=None):
    """Suppress repeats only while the last successful alert is still fresh."""
    if signal not in ("BUY", "SELL") or signal != previous:
        return False
    if (
        isinstance(last_notified_at, bool)
        or not isinstance(last_notified_at, (int, float))
        or not math.isfinite(float(last_notified_at))
        or last_notified_at < 0
    ):
        return False
    current = time.time() if now is None else number(now)
    if current is None:
        raise ValueError("Current time must be finite")
    age = current - float(last_notified_at)
    return age < SIGNAL_REPEAT_ALERT_SECONDS


def save_state(data):
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=BASE_DIR,
            prefix=".si_ai_state_",
            suffix=".tmp",
            delete=False
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temp_path, STATE_FILE)
        temp_path = None

    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                logger.exception("Temporary state file cleanup failed")


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    return result if math.isfinite(result) else None


def direction(result):
    if not isinstance(result, dict):
        return "WAIT"

    signal = str(result.get("signal", "WAIT")).strip().upper()

    if signal == "BUY":
        return "BUY"
    if signal in ("SELL", "SELL/EXIT", "EXIT"):
        return "SELL"

    return "WAIT"


def valid_risk(market, signal, result):
    price = number(result.get("price"))
    stop_loss = number(result.get("stop_loss"))
    take_profit = number(result.get("take_profit"))
    reward_risk = number(result.get("reward_risk"))

    if None in (price, stop_loss, take_profit, reward_risk):
        return False

    if min(price, stop_loss, take_profit) <= 0:
        return False

    if reward_risk < float(smc.MIN_REWARD_RISK):
        return False

    if signal == "BUY":
        return stop_loss < price < take_profit

    if signal == "SELL" and market == "FUTURES":
        return take_profit < price < stop_loss

    return False


def confirm_signal(market, results, combined):
    if not isinstance(combined, dict):
        return "WAIT"

    signal_1h = direction(results.get("1h"))
    signal_4h = direction(results.get("4h"))
    signal_mtf = str(
        combined.get("overall_signal", "WAIT")
    ).strip().upper()

    if signal_mtf not in ("BUY", "SELL"):
        return "WAIT"

    if signal_1h not in ("BUY", "SELL"):
        return "WAIT"

    if signal_1h != signal_4h or signal_1h != signal_mtf:
        return "WAIT"

    # The 1h chart is the entry setup: require a confirmed directional
    # structure break, not a score-only BUY/SELL assembled from lagging
    # indicators. The 4h chart remains the directional confirmation.
    entry_setup = results.get("1h") or {}
    expected_bos = "Bullish" if signal_1h == "BUY" else "Bearish"
    if str(entry_setup.get("bos", "None")).strip().title() != expected_bos:
        return "WAIT"

    # Futures BUY and SELL both require validated risk levels.
    if not valid_risk(market, signal_1h, results["1h"]):
        return "WAIT"

    return signal_1h


def notification_id(market, symbol):
    # Stable across Python processes and independent of the dynamic list order.
    import zlib
    return 100000 + (
        zlib.crc32(f"{market}|{symbol}".encode("utf-8")) % 900000
    )


COIN_NAMES = {
    "BTC": "Bitcoin", "ETH": "Ethereum", "BNB": "BNB",
    "SOL": "Solana", "XRP": "XRP", "ADA": "Cardano",
    "DOGE": "Dogecoin", "TRX": "TRON", "AVAX": "Avalanche",
    "LINK": "Chainlink", "DOT": "Polkadot", "LTC": "Litecoin",
    "BCH": "Bitcoin Cash", "UNI": "Uniswap", "ATOM": "Cosmos",
    "ETC": "Ethereum Classic", "XLM": "Stellar", "NEAR": "NEAR Protocol",
    "APT": "Aptos", "ARB": "Arbitrum", "OP": "Optimism",
    "SUI": "Sui", "FIL": "Filecoin", "ICP": "Internet Computer",
    "AAVE": "Aave", "INJ": "Injective", "RENDER": "Render",
    "FET": "Artificial Superintelligence Alliance", "TON": "Toncoin",
    "SHIB": "Shiba Inu", "PEPE": "Pepe", "WIF": "dogwifhat",
    "PENGU": "Pudgy Penguins", "SEI": "Sei", "TIA": "Celestia",
    "MKR": "Maker", "RUNE": "THORChain", "GRT": "The Graph",
    "VET": "VeChain", "ALGO": "Algorand", "HBAR": "Hedera",
    "EOS": "EOS", "XTZ": "Tezos", "SAND": "The Sandbox",
    "MANA": "Decentraland", "AXS": "Axie Infinity",
    "CRV": "Curve DAO", "SNX": "Synthetix", "DYDX": "dYdX",
    "EGLD": "MultiversX", "KAVA": "Kava", "ZEC": "Zcash",
    "XMR": "Monero", "DASH": "Dash", "COMP": "Compound",
    "LDO": "Lido DAO", "JUP": "Jupiter", "PYTH": "Pyth Network",
    "WLD": "Worldcoin", "ONDO": "Ondo", "ENA": "Ethena",
    "PENDLE": "Pendle", "FLOKI": "Floki", "BONK": "Bonk",
}


def coin_display_name(symbol):
    base_asset = str(symbol).split("/", 1)[0].upper()
    return COIN_NAMES.get(base_asset, "Unknown asset")


def make_alert(market, symbol, signal, results):
    reference = results["1h"]
    price = number(reference.get("price"))

    display_signal = signal

    lines = [
        f"Coin: {coin_display_name(symbol)} ({symbol})",
        f"Market: {market}",
        f"Confirmed signal: {display_signal}",
        "Entry timeframe: 1h",
        "Confirmation timeframe: 4h",
        f"1h: {direction(results['1h'])}",
        f"4h: {direction(results['4h'])}",
    ]

    if price is not None:
        lines.append(f"Entry price reference (last closed 1h candle): {price:g}")
        lines.append("Actual fill may differ; verify live price before manual entry.")

    if signal == "BUY" or market == "FUTURES":
        stop_loss = number(reference.get("stop_loss"))
        take_profit = number(reference.get("take_profit"))
        reward_risk = number(reference.get("reward_risk"))
        risk_distance = (
            abs(price - stop_loss)
            if price is not None and stop_loss is not None
            else None
        )

        lines.append(
            f"Stop Loss: {stop_loss:g}"
            if stop_loss is not None else "Stop Loss: unavailable"
        )
        if (
            price is not None and stop_loss is not None
            and take_profit is not None and risk_distance is not None
            and risk_distance > 0
        ):
            if signal == "BUY":
                tp1 = price + risk_distance
                tp2 = price + 1.5 * risk_distance
            else:
                tp1 = price - risk_distance
                tp2 = price - 1.5 * risk_distance
            lines.extend([
                f"TP1 (1R reference): {tp1:g}",
                f"TP2 (1.5R reference): {tp2:g}",
                f"TP3 (engine target): {take_profit:g}",
                "Targets are reference levels; no automatic partial exits.",
            ])
        else:
            lines.append(
                f"Take Profit: {take_profit:g}"
                if take_profit is not None else "Take Profit: unavailable"
            )
        lines.append(
            f"Reward/Risk: {reward_risk:.2f}:1"
            if reward_risk is not None else "Reward/Risk: unavailable"
        )
        if market == "FUTURES":
            leverage = number(reference.get("recommended_leverage"))
            margin = number(reference.get("paper_margin_required_usdt"))
            budget = number(reference.get("paper_margin_budget_usdt"))
            if leverage is not None:
                lines.append(f"Recommended leverage: {leverage:g}x (conservative; higher leverage disabled)")
            if margin is not None and budget is not None:
                lines.append(f"Estimated margin: {margin:.2f} USDT / {budget:.2f} USDT budget (20% of 100 USDT reference wallet)")

            quantity = number(reference.get("paper_quantity"))
            notional = number(reference.get("paper_notional_usdt"))
            gross_risk = number(reference.get("paper_risk_usdt"))
            total_risk = number(reference.get("paper_total_risk_usdt"))
            estimated_fees = number(reference.get("paper_estimated_fees_usdt"))
            estimated_slippage = number(reference.get("paper_estimated_slippage_usdt"))
            base_asset = str(symbol).split("/", 1)[0]
            if quantity is not None and notional is not None:
                lines.append(
                    f"Position size (paper estimate): {quantity:.8g} {base_asset}"
                )
                lines.append(f"Position notional (paper estimate): {notional:.4f} USDT")
            else:
                lines.append("Position size: unavailable; do not estimate manually from this alert")
            if gross_risk is not None and total_risk is not None:
                lines.append(
                    f"Estimated stop risk: {total_risk:.4f} USDT incl. estimated costs "
                    f"(gross price risk {gross_risk:.4f} USDT)"
                )
                lines.append(
                    f"Risk policy: {smc.RISK_PER_TRADE_PERCENT:.2f}% of "
                    f"{smc.PAPER_EQUITY_USDT:.2f} USDT reference equity"
                )
            if estimated_fees is not None and estimated_slippage is not None:
                lines.append(
                    f"Estimated round-trip fees: {estimated_fees:.4f} USDT; "
                    f"slippage allowance: {estimated_slippage:.4f} USDT"
                )
            lines.append(
                "Liquidation price: NOT MODELLED/NOT CERTIFIED. Keep 1x leverage; "
                "manually verify Binance margin mode and maintenance-margin rules."
            )


    reasons = reference.get("reasons", [])
    if isinstance(reasons, (list, tuple)):
        for reason in reasons[:3]:
            lines.append(f"Reason: {str(reason)}")

    return display_signal, "\n".join(lines)


def notification_command(market, symbol, title, content):
    signal = str(title).strip().upper()
    if signal not in ("BUY", "SELL", "WAIT"):
        raise ValueError(f"Unsupported notification signal: {title}")

    # Android/Termux can show a colored signal glyph in the title. LED color
    # is best-effort because many modern phones have no notification LED or
    # Android/OEM notification settings may override it.
    signal_style = {
        "BUY": {
            "title": "🟢 BUY",
            "led": "00C853",
            "vibrate": "0,120,80,120",
            "priority": "high",
            "sound": True,
        },
        "SELL": {
            "title": "🔴 SELL",
            "led": "FF1744",
            "vibrate": "0,350,100,350",
            "priority": "high",
            "sound": True,
        },
        "WAIT": {
            "title": "⚪ WAIT",
            "led": None,
            "vibrate": None,
            "priority": "default",
            "sound": False,
        },
    }[signal]

    command = [
        "termux-notification",
        "--id", str(notification_id(market, symbol)),
        "--title", f"SI-AI | {signal_style['title']}",
        "--content", content,
        "--group", "SI-AI",
        "--priority", signal_style["priority"],
    ]

    if signal_style["led"]:
        command.extend([
            "--led-color", signal_style["led"],
            "--led-on", "700",
            "--led-off", "400",
        ])

    if signal_style["vibrate"]:
        command.extend(["--vibrate", signal_style["vibrate"]])

    if signal_style["sound"]:
        command.append("--sound")

    return command


def send_notification(market, symbol, title, content):
    if shutil.which("termux-notification") is None:
        raise RuntimeError(
            "termux-notification command not found. Install the Termux:API "
            "package and companion app, then grant notification permission."
        )

    subprocess.run(
        notification_command(market, symbol, title, content),
        check=True,
        capture_output=True,
        text=True,
        timeout=15
    )


def run_cycle(dry_run=False):
    state = load_state()
    previous_signals = state["last_signals"]
    previous_notified_at = state["last_notified_at"]
    updated_signals = dict(previous_signals)
    updated_notified_at = dict(previous_notified_at)
    completed_pairs = 0

    request_delay = number(
        getattr(smc, "REQUEST_DELAY_SECONDS", 0.35)
    )
    if request_delay is None or request_delay < 0:
        request_delay = 0.35

    try:
        smc.refresh_symbol_universe()
    except Exception:
        logger.exception("Coin-universe refresh failed; no scans performed")
        return

    for market in smc.MARKETS:
        diagnostics = getattr(smc, "MARKET_UNIVERSE_DIAGNOSTICS", {}).get(market, {})
        if diagnostics:
            logger.info(
                "%s universe filters: markets=%d, volume-qualified=%d, "
                "bookTicker-matched=%d, valid-bid-ask=%d, spread-qualified=%d, "
                "selected=%d",
                market,
                diagnostics.get("markets_seen", 0),
                diagnostics.get("volume_qualified", 0),
                diagnostics.get("book_ticker_matched", 0),
                diagnostics.get("valid_bid_ask", 0),
                diagnostics.get("spread_qualified", 0),
                diagnostics.get("selected_count", 0),
            )
        market_symbols = smc.get_symbols(market)
        if len(market_symbols) < smc.MIN_ELIGIBLE_COINS:
            logger.warning(
                "%s has only %d eligible coins; minimum is %d. Market skipped.",
                market, len(market_symbols), smc.MIN_ELIGIBLE_COINS
            )
            continue
        logger.info(
            "%s universe: %d eligible USDT coins (minimum=%d, target=%d, maximum=%d, status=%s)",
            market, len(market_symbols), smc.MIN_ELIGIBLE_COINS,
            smc.TARGET_UNIVERSE_SIZE, smc.MAX_UNIVERSE_SIZE,
            smc.MARKET_UNIVERSE_STATUS.get(market, "unknown")
        )
        for symbol in market_symbols:
            key = f"{market}|{symbol}"
            results = {}
            complete = True

            logger.info("Analyzing %s", key)

            for index, timeframe in enumerate(smc.TIMEFRAMES):
                try:
                    candles = smc.get_candles(market, symbol, timeframe)
                    if not candles:
                        raise RuntimeError(f"No candles for {timeframe}")

                    result = smc.analyze_candles(
                        market, symbol, timeframe, candles
                    )
                    if not isinstance(result, dict):
                        raise RuntimeError(
                            f"Invalid analysis result for {timeframe}"
                        )

                    results[timeframe] = result

                except Exception:
                    logger.exception(
                        "Analysis failed: %s %s %s",
                        market, symbol, timeframe
                    )
                    complete = False
                    break

                if index < len(smc.TIMEFRAMES) - 1:
                    time.sleep(request_delay)

            if not complete:
                logger.warning(
                    "%s skipped; saved signal state preserved", key
                )
                continue

            try:
                combined = smc.combine_timeframes(
                    [results[tf] for tf in smc.TIMEFRAMES]
                )
                if not isinstance(combined, dict):
                    raise RuntimeError("Invalid combined timeframe result")

                signal = confirm_signal(market, results, combined)

            except Exception:
                logger.exception("Confluence analysis failed for %s", key)
                continue

            completed_pairs += 1
            previous = previous_signals.get(key, "WAIT")

            logger.info(
                "%s | 1h=%s | 4h=%s | MTF=%s | CONFIRMED=%s",
                key,
                direction(results["1h"]),
                direction(results["4h"]),
                combined.get("overall_signal", "WAIT"),
                signal
            )

            if signal == "WAIT":
                updated_signals[key] = "WAIT"
                updated_notified_at.pop(key, None)
                # Alert only on a transition from an actionable signal to WAIT;
                # this avoids flooding the phone with hundreds of initial WAITs.
                if previous in ("BUY", "SELL"):
                    wait_content = (
                        f"{market} | {symbol}\n"
                        "Signal changed to WAIT. Entry conditions are no longer confirmed.\n"
                        "Do not open a new position. Review any existing position manually."
                    )
                    if dry_run:
                        logger.info("DRY RUN WAIT ALERT: %s\n%s", key, wait_content)
                    else:
                        try:
                            send_notification(market, symbol, "WAIT", wait_content)
                            logger.info("%s: WAIT transition notification sent", key)
                        except Exception:
                            logger.exception("%s: WAIT notification failed", key)
                            updated_signals[key] = previous
                continue

            # Dry-run always previews actionable signals, even if previously alerted.
            if not dry_run and should_suppress_duplicate(
                signal, previous, previous_notified_at.get(key)
            ):
                logger.info("%s: duplicate alert suppressed (last alert is fresh)", key)
                continue

            title, content = make_alert(
                market, symbol, signal, results
            )

            if dry_run:
                logger.info(
                    "DRY RUN PREVIEW: %s\n%s", key, content
                )
                continue

            try:
                send_notification(market, symbol, title, content)
                updated_signals[key] = signal
                updated_notified_at[key] = time.time()
                logger.info("%s: notification sent", key)

            except Exception:
                logger.exception(
                    "%s: notification failed; saved state unchanged", key
                )

    if not dry_run and (
        updated_signals != previous_signals
        or updated_notified_at != previous_notified_at
        or state.get("version") != STATE_VERSION
    ):
        state["version"] = STATE_VERSION
        state["last_signals"] = updated_signals
        state["last_notified_at"] = updated_notified_at
        save_state(state)

    logger.info(
        "Cycle complete. Successfully analyzed pairs: %d",
        completed_pairs
    )


def main():
    parser = argparse.ArgumentParser(
        description="SI-AI dynamic Binance USDT signal scanner"
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--interval", type=int, default=120)

    args = parser.parse_args()

    if args.interval < 60:
        parser.error("--interval must be at least 60 seconds")

    try:
        validate_config()
        setup_logging()
        lock_handle = acquire_lock()
    except Exception as exc:
        print(f"SI-AI SCANNER STOPPED: {exc}", file=sys.stderr)
        return 1

    try:
        logger.info(
            "Scanner started | dry_run=%s | interval=%s",
            args.dry_run, args.interval
        )

        while True:
            try:
                run_cycle(dry_run=args.dry_run)
            except Exception:
                logger.exception("Scan cycle stopped by an error")
                return 1

            if args.once:
                break

            time.sleep(args.interval)

    except KeyboardInterrupt:
        logger.info("Scanner stopped by user")

    finally:
        lock_handle.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
