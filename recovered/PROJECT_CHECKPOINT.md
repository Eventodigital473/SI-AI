# SI-AI Recovery Checkpoint

**Date:** 2026-11-17  
**Repository:** `Eventodigital473/SI-AI`  
**Recovery branch:** `recovery/restore-upload-zip`  
**Baseline:** `main` at `a395f10c55dedd1faae00c70d02d8b604bedfd08`

## Recovery status

- Original ZIP verified against Git blob SHA `c74988400c975a46504aed1e1310c50e14cb3016`.
- Restored all 10 source files under `recovered/SI-AI/`.
- Preserved `UPLOAD_INSTRUCTIONS.txt` under `recovered/UPLOAD_INSTRUCTIONS.txt`.
- Added `RESTORE_MANIFEST.txt` with SHA-256 checksums for all 11 recovered files.
- `main` was not modified. All recovery work is isolated on this branch.

## Automated validation

GitHub Actions run: [SI-AI Recovery Tests](https://github.com/Eventodigital473/SI-AI/actions/runs/43971814154)

- Python 3.12 dependency installation: passed.
- `python -m compileall -q .`: passed.
- `python -m pytest -q`: **20 passed**.
- These are offline/unit tests; they do not validate live Binance data, execution quality, exchange fills, or liquidation calculations.

## Confirmed project safety requirements

- SI-AI is a signal provider only.
- No automatic Binance order placement is permitted.
- User manually reviews and executes any trade.
- Local Android/Termux notifications are the intended alert channel.
- Do not add Telegram integration or commit credentials, API keys, runtime state, or logs.

## Preliminary review observations (not yet corrected)

1. `SI_AI_smc.py` is the newer analysis/risk engine used by `main.py` and `si_ai_scanner.py`.
2. `smc.py` is a separate older SMC implementation with different signal/risk logic; clarify its role before consolidating or removing it.
3. `market.py` calls `get_market()` at module import time, causing a live network request when imported.
4. Current paper risk settings are equity 1000 USDT, 0.5% risk, 2.0x maximum notional-equity multiple, and minimum 2:1 reward/risk. These are simulation assumptions, not account-specific settings.
5. The current README explicitly says the risk estimates are not account-specific and no exchange-confirmed liquidation calculations are provided. Leverage/liquidation guidance remains unimplemented and must not be guessed.

## Next steps

1. Complete a line-by-line audit of the SMC engine, position sizing, fees/slippage, scanner state, and notification handling.
2. Review and expand tests around edge cases, stale candles, signal confirmation, and risk limits.
3. Resolve duplicate/legacy module responsibilities and import-time network side effects without deleting user code prematurely.
4. Add leverage/liquidation-risk reporting only after exchange-specific contract assumptions and calculations are independently validated.
5. Run one consolidated regression suite and update this checkpoint.
6. Only after review, prepare a pull request. Do not merge recovery work into `main` until explicitly reviewed.

**Current phase:** Archive recovery and baseline tests complete. Code audit is in progress; no trading logic has been changed.


## Dynamic coin-universe implementation checkpoint (2026-11-17)

**Working branch:** `feature/dynamic-coin-universe` (based on `recovery/restore-upload-zip`)

- Replaced the fixed BTC/ETH scanner loop with separate dynamic SPOT and FUTURES USDT universes.
- Added eligibility checks for active markets, USDT quote/settlement, 24-hour quote volume, bid/ask spread, and excluded stablecoin/wrapped/leveraged-token bases.
- SOL, BNB, BTC, and ETH receive inclusion priority only after passing the same filters.
- Configured minimum 15 eligible coins, target 50, maximum 100 per market; scanner skips a market below the minimum instead of fabricating candidates.
- Added 15-minute refresh and last-known-good preservation on exchange refresh failures.
- Scanner notification IDs now use stable symbol/market hashes so dynamic list reordering does not remap notifications.
- API config reports per-market symbols, status, and filter policy.
- Added offline mock-exchange tests in `test_dynamic_universe.py`.
- Added a dedicated CI workflow for this feature branch.
- No automatic order placement added. No credentials or private endpoints added.
- `main` remains untouched.

**Automated validation:** GitHub Actions pull-request run [SI-AI Dynamic Coin Universe Tests](https://github.com/Eventodigital473/SI-AI/actions/runs/43973445791) completed successfully on commit `2b54769a0704646b59c79986014ac05f49128ed9`.

- Python 3.12 dependency installation: passed.
- `python -m compileall -q .`: passed.
- `python -m pytest -q`: **27 passed in 0.90s**.
- Tests use mocked exchange metadata/tickers; they do not make live Binance requests.

**Review PR:** [#1 — Add dynamic Binance USDT coin universe for SI-AI](https://github.com/Eventodigital473/SI-AI/pull/1) is open as a draft against `recovery/restore-upload-zip`. It is not merged. GitHub reports the PR as mergeable. `main` remains at baseline `a395f10c55dedd1faae00c70d02d8b604bedfd08`.

**Remaining validation:** live public Binance discovery has not yet been smoke-tested from Termux. The 5m/10m quote-volume and 0.15% spread thresholds are initial screening settings and must be reviewed against live eligible-market counts. The offline tests do not prove current market liquidity, data quality, signal profitability, or live execution conditions.

**Next step:** run one controlled read-only live-universe smoke test from Termux, verify actual eligible counts and SOL/BNB inclusion, then review and mark the PR ready before merging into the recovery branch. Do not merge to `main` without separate explicit approval.


## Profitability-evidence framework checkpoint (2026-11-17)

**Working branch:** `feature/dynamic-coin-universe`

- Added `recovered/SI-AI/backtesting.py` with deterministic offline OHLCV backtesting.
- Signal callbacks see only the historical prefix through the signal candle close; simulated entries occur at the next candle open.
- Intrabar ambiguity is handled conservatively: if stop and target are both touched, stop is recorded first.
- Added configurable taker fees and adverse slippage, risk-based sizing, max-notional cap, trade ledger, data SHA-256, win rate, profit factor, net P&L, expectancy, max drawdown, and trade-based Sharpe.
- Added chronological holdout and expanding-window walk-forward evaluators.
- Added optional constant per-8-hour futures funding-rate proxy. This is explicitly not historical funding data; actual historical funding series integration remains pending. Liquidation is not modelled.
- Added `test_backtesting.py` for next-open entry, conservative same-bar stop handling, no future-candle access, spot short blocking, chronological holdout, walk-forward folds, funding proxy, malformed data, and reproducible report metadata.
- No automatic order placement or private exchange access added.

**Validation status:** New tests have been committed but GitHub Actions evidence for this new head has not yet been retrieved. Do not report these tests as passed until the workflow run is confirmed. No backtest profitability result exists yet because no verified historical dataset has been evaluated.

**Remaining work:** confirm CI on the latest commit; review and correct any failures; add historical funding data support and stronger performance gates; inspect existing SMC/risk logic and duplicate legacy modules; add paper-trading evidence capture; update PR description and final checkpoint. Termux/live Binance validation remains last, as requested.


### Profitability framework CI evidence update

- Latest verified code/workflow head: `b6c239ad8bf32588094f60014f1fc403bdc9f5d1`.
- GitHub Actions run [#43975164271](https://github.com/Eventodigital473/SI-AI/actions/runs/43975164271): dependency installation passed; `compileall` passed; **35 tests passed in 2.64s**.
- JUnit evidence artifact: `si-ai-test-evidence-27`, artifact ID `14280557685`, available until 2026-12-16; uploaded ZIP SHA-256: `fb2ee134ddbfeaf2f7e1073ea7756601cde62dd30b8c1e06c6a34747e18a6a0d`.
- This proves the offline unit/regression suite passed. It does **not** prove trading profitability or live Binance behavior.
- Pull request #1 remains open and draft; not merged. `main` remains untouched.


## Profitability evidence gate update (2026-11-17)

- Added `recovered/SI-AI/profitability_gate.py`: fail-closed certification policy for chronological OOS and walk-forward evidence.
- Minimum policy: 100 OOS trades; positive net P&L and expectancy; profit factor >= 1.20; max drawdown <= 15%; three sequential walk-forward folds, each with >= 20 trades and positive net P&L.
- Missing metrics / insufficient samples are INCONCLUSIVE; observed failed thresholds are FAIL.
- Futures certification additionally requires historical timestamped funding events and liquidation/maintenance-margin modelling. Current backtester does not yet provide those, so futures certification is intentionally blocked (INCONCLUSIVE) rather than overstated.
- Added `test_profitability_gate.py` with focused tests for pass/fail/inconclusive cases and futures fail-closed behavior. These tests have been added but not yet run in this checkpoint.
- Previously reported 35-test CI evidence belongs to code head `b6c239ad8bf32588094f60014f1fc403bdc9f5d1`; do not attribute it to these new commits.
- No real historical market dataset has been tested; no profitability claim is made.
- Automatic Binance order placement remains disabled. Termux/live validation remains the final phase.


### Profitability gate CI verification (2026-11-17)

- Corrected the gate so an undersized OOS sample is `INCONCLUSIVE`, not a false `FAIL`; fold-level positive-P&L checks are also not evaluated as failures when the fold sample is too small.
- Latest verified code head: `b7566d23d381381283c0559dabbc3c184c4360de`.
- GitHub Actions PR run [#43976125312](https://github.com/Eventodigital473/SI-AI/actions/runs/43976125312): dependency installation passed, compileall passed, **41 tests passed in 0.67s**, evidence artifact uploaded.
- Matching push run [#43976112399](https://github.com/Eventodigital473/SI-AI/actions/runs/43976112399) also succeeded.
- Artifact: `si-ai-test-evidence-35`, ID `14279054453`, expires 2026-12-16. ZIP SHA-256: `24b2b57a83678b9a02a0aaf9ab98327e53a8e503d13b387cc0d1ddaaee1e5fc1`.
- Note: GitHub Actions automatically ran the repository's full configured suite on the commit (41 total). I did not separately rerun the previously completed tests manually.
- This confirms code/test checks only. No historical dataset has been run, so no strategy profitability has been proven. Futures profitability remains blocked by missing historical funding and liquidation modelling.
