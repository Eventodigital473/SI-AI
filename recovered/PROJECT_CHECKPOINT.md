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


## User risk allocation preference update (2026-11-17)

- User confirmed a **20% margin allocation** against a $100 reference wallet.
- Updated SI_AI_smc.py: paper reference equity 100 USDT; per-trade risk budget 0.5% (0.50 USDT); margin allocation cap 20% (20 USDT); conservative futures leverage recommendation 1x only. Position quantity is constrained by both risk budget and margin-derived notional cap.
- Added output fields for recommended leverage, estimated margin required, and margin budget.
- Updated backtesting.py position sizing to use the same 20% margin cap and 1x leverage assumption.
- Updated scanner actionable alerts to show SL, TP, reward/risk, futures leverage and estimated margin usage. Spot explicitly says leverage is not applicable.
- Added WAIT transition notifications only when a previously actionable BUY/SELL state becomes WAIT, to avoid flooding the device with an initial WAIT for every scanned symbol.
- Exposed risk policy in /api/config; updated risk/API tests to assert the 100 USDT / 20 USDT policy and 1x conservative leverage.
- Important: $100 is a static reference balance, not read from Binance. 20 USDT is a cap, not a requirement to use all of it. Higher futures leverage is intentionally not recommended until historical funding and exchange-specific maintenance-margin/liquidation modelling are validated. No automatic orders.
- CI status for these latest changes: pending at checkpoint creation; do not claim tests passed until the latest head's workflow is confirmed.


### 20% margin policy CI verification (2026-11-17)

- Latest verified code head: 4c97cc318329dbe55007c8defddd50a0c75c94d4.
- GitHub Actions run [#43977270951](https://github.com/Eventodigital473/SI-AI/actions/runs/43977270951) succeeded: dependencies, compileall, **42 tests passed in 1.65s**, evidence artifact upload succeeded.
- Evidence artifact: si-ai-test-evidence-51, ID 14282005208; ZIP SHA-256 f768ecc976b78082aa7f5e3684d3a3dd8dbb7620767bb5a729bfa54802e95219.
- CI includes the new $100 reference-wallet/20% margin cap, 1x conservative leverage, backtest sizing alignment, API risk-policy exposure, and updated sizing assertions.
- This is software test evidence only. It does not validate real exchange liquidation or establish profitability. No automatic trading.


## Reliability and alert/backtest corrections (2026-11-17)

- Scanner alerts now show the coin name when it is in the curated asset map; unknown assets are explicitly labelled "Unknown asset" while retaining the exact Binance symbol rather than guessing a name.
- Actionable BUY/FUTURES alerts now show SL, three clearly labelled reference targets (TP1 at 1R, TP2 at 1.5R, TP3 at the engine's validated final target), reward/risk, and the entry/confirmation timeframes. TP1/TP2 are reference levels only; SI-AI does not execute partial exits.
- Entry price is labelled as the last closed 1h candle reference, with a warning that the manual fill may differ from the market price.
- Corrected chronological holdout and walk-forward boundaries so the first OOS entry occurs on the first test candle using only pre-test candles to form the signal. This removes the boundary look-ahead identified during audit.
- Improved stop-loss gap simulation: when a bar opens beyond the stop trigger, the backtest exits at the worse opening price (plus adverse slippage), not at the more favourable stop trigger.
- CI workflow now runs on PR updates only, with concurrency cancellation, to avoid duplicate push + PR runs for the same change. The recovery branch's independent recovery workflow remains unchanged.
- Added/updated regression tests for stop-gap fills and the first OOS signal/entry boundary.
- Pending verification: run consolidated GitHub Actions suite on this commit; continue engine/scanner audit, exchange-specific funding/liquidation modelling, real historical-data evaluation, paper-trading evidence, and final Termux read-only validation.
- No automatic orders. No claim of profitability. Main and PR merge status unchanged.


### Additional live-data safety and alert tests (2026-11-17)

- Added closed-candle freshness validation before live analysis. Stale series older than two timeframe intervals and implausibly future-dated series now fail closed instead of generating signals.
- Added focused tests for fresh/stale/future candle timestamps.
- Added dedicated signal-alert tests for coin/symbol identity, 1h entry and 4h confirmation timeframes, entry reference, SL, TP1/TP2/TP3, leverage/margin, short-side target direction, spot exit-only behavior, and unknown-name handling.
- Pending: consolidated CI verification. Live exchange smoke testing remains deferred to the final phase.


### Historical-analysis compatibility and import-safety update (2026-11-17)

- Decoupled historical candle analysis from the current live coin-universe membership check. The analysis engine now validates canonical BASE/USDT syntax; live API requests remain restricted by main.py's dynamic-universe validation and the scanner still only scans selected symbols.
- Added regression tests proving historical symbols outside today's live universe can be backtested, while malformed/non-USDT symbols are rejected.
- Removed the legacy market.py import-time network request; the standalone ticker fetch now runs only when the module is executed directly.
- Added an import-safety test that fails if importing market.py calls the exchange ticker endpoint.
- Pending verification: CI on the latest commit; deeper indicator/risk review, historical funding/liquidation modelling, real data backtests, paper-trading, and final Termux validation remain.


### Independent market-universe refresh recovery (2026-11-17)

- Changed refresh scheduling to track SPOT and FUTURES independently. A temporary failure on one exchange no longer waits for the other market's successful refresh timer before retrying.
- Last-known-good symbols remain preserved on a failed market refresh; the failed market is retried on the next scanner cycle while the healthy market retains its 15-minute cache.
- Added a regression test for partial exchange failure followed by recovery.
- Pending: CI verification and continued review. No live exchange claim is made.


### Configuration initialization ordering correction (2026-11-17)

- During review of the independent refresh change, caught that its per-market refresh timestamp dictionary was initialized before MARKETS. Moved initialization immediately after MARKETS is defined.
- This correction is included before accepting CI evidence for the latest head; earlier CI results are not attributed to this correction.


### Funding-proxy and evidence-gate correctness (2026-11-17)

- Corrected the optional funding-rate proxy to count actual UTC 00:00, 08:00, and 16:00 settlement boundaries crossed while a position is open, rather than dividing elapsed holding time by eight hours. The report now explicitly states that it holds entry notional constant and is not historical exchange funding.
- Corrected profitability-gate aggregation so missing or undersized fold evidence yields INCONCLUSIVE instead of being incorrectly promoted to a FAIL by the aggregate positive-fold check.
- Added regression tests for funding-boundary timing and missing walk-forward fold metrics.
- Futures certification remains blocked until timestamped historical funding and exchange-specific liquidation/maintenance-margin modelling are integrated.


### Strict active-market and wrapped/stablecoin filtering (2026-11-17)

- Universe discovery now requires market metadata to explicitly confirm active status; missing/unknown status is excluded rather than treated as active.
- Expanded stablecoin/fiat and wrapped-asset base exclusions.
- Added mock-exchange assertions for inactive, unknown-status, and wrapped assets.
- Pending: CI verification and continued end-to-end review.


### API multi-timeframe fail-closed correction (2026-11-17)

- Multi-timeframe API now rejects duplicate or invalid timeframe inputs.
- If any requested timeframe fails, successful partial analyses are still returned for diagnosis, but combined confluence is explicitly marked INCOMPLETE and overall signal is forced to WAIT. Partial data can no longer create an actionable combined BUY/SELL.
- Fully successful requests are marked COMPLETE. Spot bearish signals are labelled SELL/EXIT only when the full requested timeframe set succeeded.
- Added regression tests for incomplete-confluence WAIT behavior, complete responses, and duplicate timeframe rejection.
- Pending: latest CI verification.


### Scanner configuration safety and alert documentation (2026-11-17)

- Scanner startup validation now verifies the stale-candle guard is present and enforces the user-confirmed 0.5% per-trade risk, 20% margin cap, and conservative 1x futures leverage.
- Added tests to ensure a changed risk policy or missing freshness guard prevents scanner startup.
- Updated README with the exact alert fields, entry/confirmation timeframe meaning, TP reference-level caveat, manual-fill warning, spot exit-only behavior, stale-candle handling, and incomplete multi-timeframe WAIT behavior.
- Pending: latest consolidated CI and remaining end-to-end review.


## Session checkpoint — reliability audit (2026-11-17)

**Latest verified code head before this checkpoint update:** `39276d030aac8d8343312b109521d32e3845a7d9`

**Verified CI:** [Run #43981533016](https://github.com/Eventodigital473/SI-AI/actions/runs/43981533016) succeeded on the exact code head above.
- Python 3.12 dependencies installed.
- `python -m compileall -q .`: passed.
- `python -m pytest -q --junitxml=test-results.xml`: **60 passed, 4 subtests passed in 1.18s**.
- Evidence artifact: [si-ai-test-evidence-64](https://github.com/Eventodigital473/SI-AI/actions/runs/43981533016/artifacts/14281774341), ID `14281774341`, SHA-256 `af2939ff5a9c63ea2bae3d9a88ae872a3eb76a937c7936ab1a2d5b7fb75ea72f`.
- This is offline code/test evidence only; it does not prove live exchange reliability or profitability.

**Files changed in this session:**
- `recovered/SI-AI/si_ai_scanner.py`: coin identity, explicit entry/confirmation timeframe, entry reference caveat, TP1/TP2/TP3 reference targets, startup policy validation.
- `recovered/SI-AI/SI_AI_smc.py`: candle freshness checks, independent market refresh timers, stricter active/wrapped/stablecoin filtering, historical-analysis decoupling.
- `recovered/SI-AI/backtesting.py`: OOS boundary correction, stop-gap fill correction, UTC funding-boundary proxy correction.
- `recovered/SI-AI/profitability_gate.py`: missing/undersized fold evidence remains INCONCLUSIVE.
- `recovered/SI-AI/main.py`: incomplete multi-timeframe requests force WAIT; duplicate timeframes rejected.
- `recovered/SI-AI/market.py`: no network request at import time.
- Added/updated tests: scanner alerts, freshness, market refresh recovery, historical symbol validation, import safety, backtest gaps/OOS/funding boundaries, API incomplete confluence and risk policy.
- Updated `.github/workflows/dynamic-coin-tests.yml` to PR-only checks with concurrency cancellation; README updated.

**Still pending:**
1. Public historical OHLCV downloader/cache with dataset integrity and reproducible backtest runs.
2. Historical timestamped Binance futures funding integration; current constant-rate proxy is not historical funding.
3. Exchange-specific maintenance-margin/liquidation model; futures profitability gate must remain INCONCLUSIVE until verified.
4. Paper-trading journal and forward observation; no profitability claims before evidence.
5. Final read-only Termux/Binance public-data smoke test, notification check and recovery/backup check.

**Exact next step:** implement and test the public historical OHLCV data ingestion/cache for spot first, then use those verified datasets for chronological holdout and walk-forward reports. Keep futures certification blocked until historical funding and liquidation modelling are complete.

**Safety/state:** no automatic orders, no private API keys, no Telegram. Main remains untouched. PR #1 remains open, draft and unmerged. Current working branch is `feature/dynamic-coin-universe`. The verified code backup is the GitHub commit above; this checkpoint update is documentation-only.


## Historical OHLCV ingestion implementation (2026-11-17)

- Added `historical_data.py` for public Binance SPOT and linear USDT perpetual OHLCV downloads.
- Pagination is bounded and progress-checked; timestamps are normalized and strictly ordered; malformed OHLCV, inactive markets, wrong contract types, incomplete candles, and empty results fail closed.
- End timestamp is exclusive. Only fully closed candles are retained.
- Added local JSON dataset save/load with atomic writes, schema version, candle count, metadata, and SHA-256 integrity verification.
- Historical datasets are stored under `data/historical/` and excluded by .gitignore; do not commit downloaded market history.
- Added fake-exchange tests for pagination, futures symbol resolution, incomplete-candle exclusion, invalid metadata, non-progress, malformed OHLCV, and checksum tampering.
- Pending: CI verification, then a report CLI and real historical dataset acquisition only after final Termux/live-read-only phase approval.
- No API keys, private endpoints, or order placement.


### Historical dataset checksum normalization correction (2026-11-17)

- Initial historical-ingestion CI found one checksum test mismatch: raw integer OHLCV values and normalized float values represented the same candle data but produced different JSON hashes.
- Updated dataset SHA-256 to normalize every candle before hashing and to reject empty, duplicate, or unordered datasets. The fix is pending fresh CI verification.


- Hardened the checksum-tampering test to alter only volume while preserving valid OHLC relationships, so the expected failure specifically verifies SHA-256 integrity rather than malformed-candle validation.


## Historical validation report runner (2026-11-17)

- Added `historical_backtest.py` to load and checksum-verify a saved dataset, run chronological holdout and expanding-window walk-forward validation, evaluate the fail-closed profitability gate, and atomically write a reproducible JSON report.
- Insufficient-data validation errors are represented as INCONCLUSIVE, not as successful performance.
- Futures gate remains INCONCLUSIVE without historical funding and liquidation/maintenance-margin evidence.
- Added tests for successful report plumbing, futures fail-closed behavior, and insufficient-data handling. Positive test fixtures are synthetic and do not represent market returns.
- Reports are saved under git-ignored `data/reports/`.
- Pending: CI verification, then actual historical datasets must be downloaded in the final read-only live-data phase; no profitability claim yet.


### Historical dataset window-boundary validation (2026-11-17)

- Historical downloads now exclude candles whose close time extends beyond the requested exclusive end timestamp, not merely candles whose open time is after it.
- Dataset save/load now validates canonical market/symbol/timeframe metadata and declared time bounds; corrupted or inconsistent metadata fails closed.
- Added regression tests for partial end intervals and datasets outside declared windows.
- Pending CI verification.


### Historical delisted-market research compatibility (2026-11-17)

- Historical downloader now accepts an explicitly identified inactive/delisted market when Binance still exposes its metadata and public OHLCV history. Unknown/missing active status is still rejected.
- Live dynamic-universe selection continues to require active=true. Historical research is separated from current live eligibility to reduce survivorship bias.
- Added regression test for known inactive historical markets.
- Pending CI verification.


### Live-candle market-status and API signal-scope guard (2026-11-17)

- Live `get_candles` now independently verifies active status, USDT quote, and the correct spot or linear USDT perpetual contract type before fetching data. This prevents a preserved last-known-good universe from scanning a market that has since become inactive.
- Historical downloader remains separate and may use explicitly known inactive markets for historical research only.
- Single-timeframe API responses are now labelled unconfirmed and explicitly require multi-timeframe confirmation; the scanner's confirmed 1h/4h alert process is unchanged.
- Added tests for inactive live-market rejection, closed-candle return, and single-timeframe API scope.
- Pending: latest CI verification.


## Historical research pipeline verification checkpoint (2026-11-17)

**Verified code head:** `0b947b7a16b8e7bbcce8bfd30502dcbf69cd2b36`

**Latest GitHub Actions evidence:** [Run #43983550669](https://github.com/Eventodigital473/SI-AI/actions/runs/43983550669)
- Python 3.12 dependency installation: passed.
- `python -m compileall -q .`: passed.
- Full pytest suite: **76 passed, 4 subtests passed in 1.32s**.
- Evidence artifact: [si-ai-test-evidence-72](https://github.com/Eventodigital473/SI-AI/actions/runs/43983550669/artifacts/14283329312), ID `14283329312`, SHA-256 `7137a57d45aea9642013816e546aa48545e785887edb8f2ce2b32d2a8bbb00a8`.

**New historical research components:**
- `historical_data.py`: public Binance OHLCV downloader for SPOT and linear USDT perpetuals; bounded pagination, strict OHLCV validation, closed-candle-only filtering, exclusive end-time validation, historical inactive-market support only when exchange metadata explicitly identifies status, atomic local dataset storage, and SHA-256 verification.
- `historical_backtest.py`: checksum-verified dataset loader, chronological holdout, expanding walk-forward, fail-closed profitability gate, and atomic JSON report.
- `test_historical_data.py` and `test_historical_backtest.py`: pagination, market resolution, incomplete candle/window exclusion, checksum tampering, report generation, and futures fail-closed tests.
- Local datasets/reports are git-ignored under `data/historical/` and `data/reports/`.

**Remaining blockers:**
1. No real historical dataset has yet been downloaded or evaluated. Existing historical-data tests use synthetic fixtures only.
2. Futures profitability remains INCONCLUSIVE until timestamped historical funding and exchange-specific maintenance-margin/liquidation modelling are implemented and verified.
3. Forward paper-trading observation and signal-quality review remain pending.
4. Final read-only Termux/Binance public-data and Android notification smoke test remains last.

**Exact next step:** validate the historical downloader against one bounded, read-only public Binance dataset in the final live-data phase, verify its manifest/checksum, then run the report runner. Do not use synthetic fixtures as profitability evidence.

**Safety and repository state:** signal provider only; no automatic orders, no private API keys, no Telegram. Main untouched. PR #1 remains draft/open/unmerged. Verified code backup commit: `0b947b7a16b8e7bbcce8bfd30502dcbf69cd2b36`.


### Dynamic-universe target-size enforcement (2026-11-17)

- Corrected selection to target 50 symbols per market rather than scanning up to the 100-symbol hard cap by default.
- The 100-symbol maximum remains a configuration ceiling. BTC, ETH, BNB and SOL are prioritized only when they pass the same filters and replace lower-ranked candidates without exceeding the 50-symbol target.
- Added regression assertions for exact target size and core-asset inclusion. This reduces the default scanner request workload while preserving the minimum-15 and maximum-100 policy.
- Pending CI verification.


## Scanner workload tuning checkpoint (2026-11-17)

**Latest verified code head:** `1cf8575ca5cd1c0635e04805aef0129589a9bc2b`

**CI evidence:** [Run #43984040849](https://github.com/Eventodigital473/SI-AI/actions/runs/43984040849) succeeded on the exact code head.
- Python dependency installation and compileall passed.
- Full suite: **76 passed, 4 subtests passed in 0.61s**.
- Evidence artifact: [si-ai-test-evidence-74](https://github.com/Eventodigital473/SI-AI/actions/runs/43984040849/artifacts/14285101349), ID `14285101349`, SHA-256 `7235e3139b69a82d32d7d2fff223c4a87b6c8e29a4004b9fde97e1f04dd9a71e`.

**Performance correction:** dynamic scanner now targets 50 selected symbols per market, not 100 by default. 100 remains the hard configurable maximum; core assets are only prioritized when eligible and replace lower-ranked candidates without expanding the target.

**Exact next step:** perform one bounded read-only public Binance historical OHLCV download after confirming the final Termux runtime environment, validate the dataset checksum, and run `historical_backtest.py`. Do not treat synthetic tests as market-performance evidence.

**Still not production-certified:** historical sample performance, timestamped futures funding, exchange-specific liquidation/maintenance-margin model, forward paper observation, and final Termux notification/runtime checks. No automatic orders, no profitability guarantee. Main untouched; PR #1 remains draft/open/unmerged.


### Production-equivalent multi-timeframe backtest correction (2026-11-17)

- Identified that the first historical report runner used only single-timeframe SMC signals, which did not reproduce the live scanner's 15m/1h/4h/1d confluence. This was not suitable for production-strategy profitability evidence.
- Reworked the runner to require four verified datasets for the same market/symbol and to reproduce scanner confluence at each 1h signal close. Auxiliary timeframe candles are included only when their full close time is at or before the 1h signal close.
- Backtester now supports Spot SELL/EXIT closing an existing long at the next candle open and Futures opposite confirmed signals closing at the next candle open. Spot SELL never opens a short.
- Added tests for multi-timeframe no-lookahead filtering, missing timeframe warm-up, spot exit, futures reversal, all-four-dataset requirement, and report integration.
- Pending: CI verification. Futures profitability remains blocked by missing historical funding and liquidation/maintenance-margin models.


- Initial CI for production multi-timeframe runner had 80 passing tests and one assertion failure caused only by case-sensitive test wording. Updated the expected error text to match the actual fail-closed message; rerun pending.


## Session checkpoint — SMC entry/exit and net R:R correction (2026-11-17)

**Working branch:** `feature/dynamic-coin-universe`  
**Verified code head:** `2dda0a7427cc3577627fc03b58179dcf54a30a4e`

### Corrections committed
- `SI_AI_smc.py`: BOS now checks the corresponding confirmed swing level independently; a missing opposite-side pivot no longer suppresses a valid directional BOS.
- `SI_AI_smc.py`: CHOCH is treated as the classification of a counter-trend BOS and is no longer added as a second independent structure-break score.
- `si_ai_scanner.py`: confirmed scanner entries require the 1h setup to have a matching directional BOS; the 4h direction and weighted multi-timeframe agreement remain required. Spot bearish confirmation remains exit-only.
- `SI_AI_smc.py`: added shared fee/slippage-aware net reward/risk calculation for long and short setups.
- `backtesting.py`: after next-candle-open execution and adverse entry slippage, actual-fill net R:R is recalculated. Trades below 2:1 are rejected before entry.
- `backtesting.py` and `portfolio_backtest.py`: entry slippage already embedded in the entry fill is no longer charged a second time in stop-risk sizing; both-side fees and stop-exit slippage remain reserved.
- Added a small numerical tolerance at the exact 2:1 boundary to avoid rejecting valid trades due solely to floating-point representation.
- Added regression coverage for independent BOS pivots, BOS/CHOCH double counting, long/short net R:R, adverse entry gaps, favorable gaps, actual-fill R:R reporting, 1h BOS gating, and Spot exit-only behavior.

### Verified tests
- GitHub Actions PR run [#44085941561](https://github.com/Eventodigital473/SI-AI/actions/runs/44085941561) succeeded on the exact code head above.
- Python 3.12 dependency installation and `python -m compileall -q .`: passed.
- Full offline suite: **103 passed, 4 subtests passed in 1.77s**.
- Evidence artifact: `si-ai-test-evidence-111`, artifact ID `14329282352`, SHA-256 `cef0a469afbabfcbe3df4b375c43a813aaa4865e84e53f253d077477508e6583`, expires 2026-12-17.
- An earlier intermediate test run failed due to a missing local direction variable in the new helper; it was fixed. The next run exposed a floating-point boundary rejection; that was fixed too. The successful run above verifies the final code head.

### Historical backtest status
- Public Spot historical validation workflow [#44085934783](https://github.com/Eventodigital473/SI-AI/actions/runs/44085934783) is running on the same code head.
- Its full offline regression step passed; the bounded 180-day, 50-symbol Spot history download and shared-wallet portfolio backtest are still in progress. No result from this run is claimed yet.
- Previous observed portfolio baseline remains: 25 OOS trades, 16% win rate, PF 0.35, net -4.61 USDT per 100 USDT; walk-forward 45 trades, net -4.52 USDT; 54 overlapping opportunities skipped. These are the pre-correction results and must not be represented as results of the corrected code.
- The earlier universe run had 50 selected Spot symbols and 34 complete 180-day datasets. The current workflow must report its own verified symbol count and dataset hashes.

### Exact next step
1. Retrieve workflow #44085934783 when it completes; inspect its dataset manifest, checksums, OOS ledger, walk-forward folds, skipped-overlap count, and profitability-gate result.
2. Compare corrected results against the pre-correction baseline. Do not tune parameters to this same holdout or claim profitability from an undersized sample.
3. If the workflow fails or data is incomplete, diagnose only the reported failure and preserve the existing verified code/tests.
4. Keep Futures certification INCONCLUSIVE until timestamped historical funding and exchange-specific liquidation/maintenance-margin modelling are validated; then paper observation and final read-only Termux/Binance smoke checks remain.

**Safety/state:** SI-AI remains a signal provider only. User manually executes any trade. No automatic order placement, private API keys, Telegram, or deployment added. `main` remains untouched. PR #1 remains open, draft and unmerged.
