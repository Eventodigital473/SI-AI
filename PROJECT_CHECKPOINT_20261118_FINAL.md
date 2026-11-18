# SI-AI Resume Checkpoint — 2026-11-18 (latest verified CI; 730-day research pending)

## Candidate and safety
- Repository: Eventodigital473/SI-AI
- Candidate branch: `fix/scanner-risk-audit-2026-11-18`
- Current branch/PR head: `395a943ac52db1cb812eeab2c06f600588caf388`
- Latest Python code under test is on ancestor `d083ec091a343c2c84d28044237b3ef53f2feaaa`; the latest `395a943` commit only refreshes this checkpoint document.
- Draft PR: https://github.com/Eventodigital473/SI-AI/pull/17
- PR #17 is open, draft, mergeable and unmerged. Do not merge without explicit user approval.
- Futures-only; Spot excluded from the active scanner/backtest files.
- Signal/notification provider only. No automatic orders, private account endpoints or balance fetching.
- Reference equity 100 USDT; per-trade risk 0.5% (0.50 USDT); margin allocation cap 20%; leverage guidance 1x; minimum net R:R 2:1.

## Latest verified automated checks
- Latest CI on current PR head: https://github.com/Eventodigital473/SI-AI/actions/runs/44342174543 — SUCCESS.
- Exact pytest output: **231 passed, 8 subtests passed in 1.24 seconds**.
- Dependency consistency passed; minimal synchronous Termux CCXT profile passed with CCXT 4.5.93; Termux Widget shell syntax and installer preservation passed; Python compilation passed.
- Previous CI run on the exact research-code commit: https://github.com/Eventodigital473/SI-AI/actions/runs/44341693784 — SUCCESS, same 231 passed and 8 subtests.
- 730-day historical workflow: https://github.com/Eventodigital473/SI-AI/actions/runs/44341693703 — last checked 2026-11-18 16:03 UTC, still IN_PROGRESS. Dependency installation, compile, and full automated tests passed; 730-day checksum-verified Binance Vision backtest step remained in progress. No artifact was available yet. Its job-log endpoint returned NOT_FOUND while running, so no further output or completion is claimed.
- Earlier intermediate CI failures on commits `6c80f59`, `ceedcd6`, `a5bb89c`, and `ddda39f` were due to synthetic fixtures with non-UTC-aligned candle timestamps after strict coverage validation. Fixtures were corrected; later CI on `d083ec0` and `395a943` passed.
- Historical 365-day baseline run: https://github.com/Eventodigital473/SI-AI/actions/runs/44291060559 — SUCCESS.
- Core scanner static review found no Spot references in `SI_AI_smc.py` or `si_ai_scanner.py` and no `create_order`, `cancel_order`, `set_leverage`, private account, or balance calls in those core files.

## Completed changes in latest audit
1. **Profitability gate fail-open fix:** all supplied walk-forward folds are now evaluated; malformed fold entries make evidence INCONCLUSIVE. Regression tests cover a later losing fold and malformed extra fold.
2. **Binance Vision archive coverage:** requested start/end candle coverage and UTC timeframe alignment are required, in addition to checksum validation and internal continuity. Missing first/last candles cannot pass.
3. **Public OHLCV and mark-price coverage:** shared full-window coverage validation is used by historical OHLCV and mark-price downloads, saved datasets and loaded datasets. Edge gaps fail closed.
4. **Regression tests:** added edge-gap, malformed-fold, and UTC-boundary tests; synthetic fixture timestamps were aligned to real Binance UTC candle boundaries.
5. **Historical research window:** GitHub historical workflow extended from 365 to 730 days for BTC, ETH, BNB, XRP, ADA, DOGE, LINK, AVAX, DOT and SOL.

## 365-day historical validation baseline
- Workflow: https://github.com/Eventodigital473/SI-AI/actions/runs/44291060559
- Artifact: `si-ai-futures-validation-44291060559`; 71 files; 10.7 MB.
- Artifact SHA-256: `e4cf59c0018f2b7ce565b5e46aa87a6bd589a1f035d9954f20fd103a32b0460e`
- Period: 2025-11-01 through 2026-11-01 UTC (exclusive end).
- Per-symbol OOS sample: 2–8 trades; 52 trades total across independent symbol runs.
- Diagnostic sum of OOS net P&L across independent 100-USDT symbol runs: -1.892547 USDT; NOT a shared-wallet portfolio result.
- Walk-forward sample: 70 trades total across independent symbol runs; diagnostic sum net P&L -5.541666 USDT; NOT a shared-wallet portfolio result.
- OOS positive/negative symbols: 5 / 5. Walk-forward positive/negative symbols: 4 / 6.
- Every symbol profitability gate: FAIL. Overall certification: INCONCLUSIVE.
- No symbol is certified profitable. Do not present the 365-day results as evidence of a profitable system.

## Funding API audit
- Binance's official USD-M API documentation specifies that GET `/fapi/v1/fundingRate` returns `symbol`, `fundingRate`, `fundingTime`, `markPrice` (the mark price associated with a particular funding fee), and `rateType`; max page limit is 1000, ascending order. Official docs: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History
- `funding_data.py` validates and preserves raw event-specific `markPrice`; `run_public_futures_backtest.py` downloads exact funding events and passes them into historical backtesting.
- The 730-day Binance Vision runner does not yet call this API; its funding CSV is audit-only and is not applied to P&L.
- A full-period live retrieval and integration with the archive-based 730-day run remain pending. Do not claim exact funding was applied to the 730-day Vision report unless verified by its artifact/report.

## Remaining certification blockers
1. Historical maintenance-margin bracket/tier snapshots matched to each historical timestamp are unavailable in the archive workflow; no historical liquidation simulation.
2. Mark-price OHLC does not establish exact intrabar liquidation sequencing.
3. Ten symbols are currently tested with independent reference equity; no shared-wallet portfolio simulation exists.
4. 365-day OOS and walk-forward sample sizes are inadequate. Await 730-day evidence; never lower thresholds to force PASS.
5. Android/Termux runtime, live public-data connectivity and device notification/sound/vibration/LED behavior remain unverified on the user's phone.
6. Historical results do not guarantee future performance.

## Exact next steps
1. Poll workflow 44341693703 until completion. Download its artifact, verify SHA-256, inspect all ten per-symbol OOS and walk-forward reports, and record sample counts and gate statuses.
2. Validate full-period public Binance funding API retrieval (event-specific markPrice) and feed the verified dataset into the historical backtest; keep the existing Vision CSV explicitly audit-only.
3. Continue checking signal scarcity, train/OOS separation and execution assumptions without tuning against OOS data.
4. Build and test a shared-wallet multi-symbol portfolio simulator before any portfolio-level claim.
5. Keep profitability certification INCONCLUSIVE/FAIL until funding, historical liquidation, execution costs, sample thresholds and portfolio evidence genuinely pass.
6. Only after remote code/research review, prepare one isolated Termux deployment/verification step. Do not overwrite the existing `~/SI-AI_FINAL` checkout.
7. Keep PR #17 draft/unmerged until the user explicitly approves integration.

No live trading is enabled. No automatic orders are placed.
