# SI-AI Final Handoff — 2026-11-17

## Source of truth
- Repository: https://github.com/Eventodigital473/SI-AI
- Working branch: `feature/dynamic-coin-universe`
- Latest reviewed branch head: `f146290d927c00fd510dfccd2f9e59852cf525e5`
- Canonical source folder inside the repository: `recovered/SI-AI/`
- `main` was not modified by this handoff. Existing recovery and feature branches are preserved.
- This handoff adds documentation only; it does not change signal logic or trading behavior.

## Verification evidence
- Latest branch CI run: https://github.com/Eventodigital473/SI-AI/actions/runs/44090485500
- Exact head: `f146290d927c00fd510dfccd2f9e59852cf525e5`
- Python dependency installation: PASS.
- `python -m compileall -q .`: PASS.
- JUnit evidence: 115 test cases, 0 failures, 0 errors, 0 skipped.
- The tests are offline/software checks; they do not prove live execution reliability or profitability.

## Public Spot historical backtest
- Workflow: https://github.com/Eventodigital473/SI-AI/actions/runs/44090339921
- Backtest source commit: `d810b505898de71821186a181ed87e6285db99b5`.
- The later `f146290` commit only appends the separate high-leverage planner checkpoint; the Spot backtest engine, universe filters, and runner were unchanged.
- Requested history: 180 days.
- Selected Spot candidates: 49.
- Complete, aligned symbols: 33.
- Skipped for incomplete historical window: 16.
- Timeframes: 15m, 1h, 4h, 1d.
- Downloaded datasets: 132 (33 symbols x 4 timeframes).
- Independent archive verification: all 132 dataset SHA-256 hashes and candle counts matched their manifests.
- Combined dataset SHA-256: `d4f0029e20832fa14cde06181ef3f56bdf09caa9318ed1df1a439f70301c6d0a`.
- USD stablecoin bases RLUSD and XUSD are excluded from the corrected eligible universe.
- Portfolio assumptions: 100 USDT reference wallet, 0.5% planned risk budget, 20% notional cap, one concurrent Spot position, 0.10% taker fee and 0.02% adverse slippage.

### Out-of-sample result
| Metric | Result |
|---|---:|
| Trades | 15 |
| Win rate | 26.67% |
| Profit factor | 0.736373 |
| Net P&L | -0.739271 USDT |
| Expectancy | -0.049285 USDT/trade |
| Maximum drawdown | 1.7365% |
| Ending equity | 99.260729 USDT |

Walk-forward aggregate: 26 trades, +0.413217 USDT, profit factor 1.073834. The three folds had 16, 7, and 3 trades; the sample minimum is 20 per fold.

**Profitability gate: FAIL.** The OOS sample is below the 100-trade minimum, OOS net P&L and expectancy are negative, and OOS profit factor is below 1.20. Walk-forward fold samples are also insufficient. Do not call this strategy profitable or treat this report as permission for live trading. Do not tune parameters against this same holdout to force a PASS; use a new untouched holdout after any strategy changes.

Known research limitation: the current eligible-universe snapshot is applied retrospectively; historical membership is not reconstructed, so survivorship bias remains. The portfolio simulator allows one position at a time and skips overlapping opportunities.

## Futures and high-leverage boundary
- Futures profitability certification remains INCONCLUSIVE without timestamped historical funding and a validated exchange-specific maintenance-margin/liquidation model.
- `binance_high_leverage.py` is a standalone paper-only planner. It is not integrated into the live scanner and does not retrieve Binance brackets or call Binance.
- The active scanner remains at 0.5% risk, 20% allocation cap, and conservative 1x Futures leverage.
- Never paste Binance API secrets into ChatGPT. No automatic order placement, cancellation, amendment, or leverage-setting is implemented. The user manually reviews and executes any trade.

## Termux installation (safe separate folder)
These steps preserve an existing `~/SI-AI` folder. They clone the reviewed branch into a separate `~/SI-AI_FINAL` directory. If that destination already exists, choose another new directory rather than overwriting it.

```bash
pkg update -y
pkg install -y git python termux-api

cd "$HOME"
git clone --branch feature/dynamic-coin-universe --single-branch https://github.com/Eventodigital473/SI-AI.git SI-AI_FINAL

cd "$HOME/SI-AI_FINAL/recovered/SI-AI"
python -m pip install -r requirements.txt
python -m compileall -q .
python -m pytest -q
```

The Termux:API Android companion app must also be installed and notification permission granted for phone notifications. Installing the `termux-api` package alone does not install the Android companion app.

## Run modes

### 1. Safe live-data preview (no notifications)
```bash
cd "$HOME/SI-AI_FINAL/recovered/SI-AI"
python si_ai_scanner.py --once --dry-run
```
This makes public market-data requests and logs signal previews. It does not send notifications or place orders.

### 2. Continuous scanner with Android notifications
```bash
cd "$HOME/SI-AI_FINAL/recovered/SI-AI"
python si_ai_scanner.py --interval 120
```
Stop with Ctrl+C. Android notification behavior, sound, vibration, and permissions must be checked on the physical phone.

### 3. Local Flask API (separate Termux session)
```bash
cd "$HOME/SI-AI_FINAL/recovered/SI-AI"
python main.py
```
Open `http://127.0.0.1:5000/status` or `http://127.0.0.1:5000/api/config` in the phone browser. Keep the process running while using the API.

### 4. Re-run public Spot portfolio backtest
```bash
cd "$HOME/SI-AI_FINAL/recovered/SI-AI"
python run_public_spot_portfolio.py --days 180 --symbol-limit 50 --initial-equity 100
```
This downloads public Spot history and can take a long time on a phone. It writes local datasets under `data/historical/` and reports under `data/reports/`; these are git-ignored. No API key is required and no order is placed. Longer windows can be requested with `--days` (120–730), but the runner requires at least 15 symbols with complete aligned history and may correctly stop if that minimum is not met.

## Device validation still required
- Termux and Termux:API installed on the actual Android device.
- Android notification permission, sound, and vibration checked on-device.
- One dry-run scan and one controlled notification smoke test.
- These device checks have not been claimed as completed by GitHub CI.

## Completion statement
The software test suite and the first corrected 180-day multi-symbol Spot backtest have both been run and their evidence archived. The code is runnable in Termux using the steps above, but **profitability is not certified**. Keep the system in analysis/signal-only mode until fresh out-of-sample evidence and device validation are satisfactory.


## 2026-11-17 follow-up — Futures bookTicker normalization

### Current working state
- Original base branch preserved: `feature/dynamic-coin-universe`.
- Follow-up branch: `fix/futures-bookticker-normalization-2026-11-17`.
- Draft PR: https://github.com/Eventodigital473/SI-AI/pull/2
- The original `main` branch remains untouched.
- No live or automatic order-placement functionality was added.

### Diagnosis carried forward
The prior Termux checkpoint showed 182 Futures contracts passing the 10M USDT quote-volume filter, followed by 182 missing/invalid bid values. The original exchange-response root cause was not proven at that time. The 0.15% maximum spread filter was intentionally not relaxed.

### Changes in the follow-up branch
- Index bulk bookTicker entries by response key, CCXT unified symbol, ticker ID, and raw Binance `info.symbol`.
- Resolve contract quotes using unified symbol, canonical base/quote symbol, and Binance market ID.
- Parse normalized `bid`/`ask` and raw `bidPrice`/`askPrice` values, including nested `info`.
- Express midpoint-relative spread as `200 * (ask - bid) / (ask + bid)`, equivalent to `100 * (ask - bid) / midpoint`.
- Add filter-stage diagnostics: markets seen, volume-qualified, bookTicker-matched, valid bid/ask, spread-qualified, candidate count, and selected count.
- Add regression tests for alias resolution, quote normalization, spread algebra, fee/slippage-adjusted long/short reward-risk, and mocked end-to-end Futures universe refresh.
- Add GitHub Actions dependency, compilation, and pytest checks.

### Latest CI evidence
- Workflow run: https://github.com/Eventodigital473/SI-AI/actions/runs/44140620177
- Head tested: `2b1193753aaf3626d93522918b92abefc6716b28`.
- `python -m pip check`: PASS — no broken requirements.
- `python -m compileall -q .`: PASS.
- `python -m pytest -q`: **124 passed, 4 subtests passed**.
- One initial new assertion failed because it used exact float equality; changed to `pytest.approx`, then reran the complete suite successfully.

### Still required before merging
1. Update the existing Termux clone from the follow-up branch without overwriting any uncommitted local work.
2. Run `python -m pip check`, `python -m compileall -q .`, and `python -m pytest -q` on-device.
3. Run `python si_ai_scanner.py --once --dry-run` and inspect the new Futures filter-stage diagnostics.
4. Confirm that real Binance/CCXT Futures bookTicker records now match and contain valid bid/ask values. If they still do not, capture a sanitized sample of the response shape (never API secrets) and adjust the parser based on that evidence.
5. Investigate the Spot 49-versus-50 observation separately; 50 is a target, not a guaranteed count, while 15 is the fail-closed minimum.
6. Preserve the existing Spot profitability gate result: FAIL (15 OOS trades, 26.67% win rate, PF 0.736373, net P&L -0.739271 USDT). Do not tune against that same holdout or describe the strategy as profitable.

The PR remains draft and unmerged until live Termux validation is reviewed. SI-AI remains signal-only; the user manually executes trades.
