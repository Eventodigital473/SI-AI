# SI-AI Resume Checkpoint — 2026-11-18 (latest risk/data-integrity audit)

## Candidate and safety
- Repository: Eventodigital473/SI-AI
- Candidate branch: fix/scanner-risk-audit-2026-11-18
- Current branch/PR head: d083ec091a343c2c84d28044237b3ef53f2feaaa
- Draft PR: https://github.com/Eventodigital473/SI-AI/pull/17
- PR #17 is open, draft, mergeable and unmerged. Do not merge without explicit user approval.
- Futures-only; Spot excluded from the active scanner/backtest files.
- Signal/notification provider only. No automatic orders, private account endpoints or balance fetching.
- Reference equity 100 USDT; per-trade risk 0.5% (0.50 USDT); margin allocation cap 20%; leverage guidance 1x; minimum net R:R 2:1.

## Latest verified automated checks
- Latest candidate CI: https://github.com/Eventodigital473/SI-AI/actions/runs/44341693784 — SUCCESS.
- Exact test output: **231 passed, 8 subtests passed**.
- Dependency consistency, minimal synchronous Termux CCXT profile (CCXT 4.5.93), Termux Widget shell validation, Python compilation and full pytest suite all passed.
- Latest 730-day historical workflow: https://github.com/Eventodigital473/SI-AI/actions/runs/44341693703 — IN PROGRESS at checkpoint time. Its dependency, compile and full automated-test steps passed; checksum-verified Binance Vision backtest step is still running.
- Intermediate CI failures on earlier commits were caused by synthetic test fixtures using non-UTC-aligned candle timestamps after strict boundary validation was added. Test fixtures were corrected; the latest candidate CI above passes.
- Historical 365-day baseline run: https://github.com/Eventodigital473/SI-AI/actions/runs/44291060559 — SUCCESS.
- Core source static review found no Spot references in SI_AI_smc.py or si_ai_scanner.py and no create_order/cancel_order/set_leverage/private/balance calls in those files.

## Completed changes in latest audit
1. **Profitability gate fail-open fix:** previously only the first required number of walk-forward folds were evaluated. The gate now evaluates every supplied fold and marks malformed fold entries INCONCLUSIVE. Added regression tests for a later losing fold and malformed extra fold.
2. **Binance Vision archive coverage:** exact requested start/end candle coverage and timeframe alignment are now required, in addition to checksum validation and internal continuity. Missing first/last candles cannot pass.
3. **Public OHLCV and mark-price coverage:** added shared full-window coverage validation to historical_data.py and mark_price_data.py. Downloads, saved datasets and loaded datasets must cover every expected fully closed candle; edge gaps fail closed.
4. **Regression tests:** added edge-gap, malformed-fold, and UTC-boundary tests; synthetic fixture timestamps were aligned to real Binance UTC candle boundaries.
5. **Historical research window:** updated the GitHub historical workflow from 365 to 730 days for the same ten USD-M symbols. Current run ID 44341693703 is in progress.

## 365-day historical validation baseline
- Workflow: https://github.com/Eventodigital473/SI-AI/actions/runs/44291060559
- Artifact: si-ai-futures-validation-44291060559; 71 files; 10.7 MB.
- Artifact SHA-256: e4cf59c0018f2b7ce565b5e46aa87a6bd589a1f035d9954f20fd103a32b0460e
- Period: 2025-11-01 through 2026-11-01 UTC (exclusive end).
- Symbols: BTC, ETH, BNB, XRP, ADA, DOGE, LINK, AVAX, DOT, SOL.
- Per-symbol OOS sample: 2–8 trades; 52 trades total across independent symbol runs.
- Diagnostic sum of OOS net P&L across independent 100-USDT symbol runs: -1.892547 USDT; this is NOT a shared-wallet portfolio result.
- Walk-forward sample: 70 trades total across independent symbol runs; diagnostic sum net P&L -5.541666 USDT; this is NOT a shared-wallet portfolio result.
- OOS positive/negative symbols: 5 / 5. Walk-forward positive/negative symbols: 4 / 6.
- Every symbol profitability_gate: FAIL. Overall research summary certification: INCONCLUSIVE.
- All per-symbol OOS samples are far below the 100-trade gate; individual walk-forward folds contain 0–6 trades versus the required 20 per fold.
- No symbol is certified profitable. Do not present the 365-day results as evidence of a profitable system.

## Remaining certification blockers and next research
1. **Exact funding settlement prices:** Binance's official USD-M API documents that GET /fapi/v1/fundingRate returns the markPrice associated with each funding fee. Existing funding_data.py and run_public_futures_backtest.py already require and preserve that field. The exact-price public API route still needs a live 730-day retrieval/validation on the candidate environment; the Binance Vision CSV route remains audit-only and does not apply funding to P&L.
2. **Historical liquidation:** timestamp-matched historical maintenance-margin tier snapshots are still unavailable in the current archive workflow. Current bracket data must not be substituted for historical tiers; no historical liquidation certification.
3. **Intrabar liquidation sequence:** mark-price OHLC does not establish exact event ordering within a candle.
4. **Portfolio simulation:** the ten symbols use independent 100-USDT reference equity; no shared-wallet multi-symbol portfolio simulation exists.
5. **Evidence volume:** 365-day OOS and walk-forward samples are insufficient. Await the 730-day report; do not lower thresholds to force PASS.
6. **Device verification:** Android/Termux runtime, live public-data connectivity, notifications, sound/vibration and LED behavior have not been tested on the user's phone.
7. Historical results do not guarantee future performance.

## Exact next steps
1. Poll workflow 44341693703 until complete. Download its artifact, verify SHA-256, inspect all ten per-symbol OOS and walk-forward results, and record sample counts and gate status.
2. Validate the exact public funding API route with Binance USD-M funding history and per-event markPrice, ideally for the full research period; if inaccessible or incomplete, retain the fail-closed funding blocker.
3. Continue checking signal scarcity and train/OOS separation without tuning against OOS data.
4. Build and test a shared-wallet multi-symbol portfolio simulator before any portfolio-level claim.
5. Keep the profitability gate INCONCLUSIVE/FAIL until funding, historical liquidation, execution costs, sample thresholds and portfolio evidence are genuinely satisfied.
6. Only after remote code/research review, prepare one final isolated Termux deployment/verification step. Do not overwrite the existing ~/SI-AI_FINAL checkout.
7. Keep PR #17 draft/unmerged until the user explicitly approves integration.

No live trading is enabled. No automatic orders are placed.
