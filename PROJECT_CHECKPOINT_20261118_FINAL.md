# SI-AI Resume Checkpoint — 2026-11-18 (updated after 365-day validation)

## Candidate and safety
- Repository: Eventodigital473/SI-AI
- Candidate branch: fix/scanner-risk-audit-2026-11-18
- Current branch/PR head: 3629d28e2f9f64880fcff1f181bf2cf0664f29a8 (checkpoint-document-only commit after validated code).
- Historical validation code head: 853d758e3ea75ade96cd2bfdaad66dccd88cce61; its Python code is unchanged from 3aa29bf61d934ca480915c64b910f2989aec617c.
- Draft PR: https://github.com/Eventodigital473/SI-AI/pull/17
- PR #17 is open, draft, mergeable and unmerged. Do not merge without explicit user approval.
- Futures-only; Spot excluded from the active scanner/backtest files.
- Signal/notification provider only. No automatic orders, private account endpoints or balance fetching.
- Reference equity 100 USDT; per-trade risk 0.5%; margin allocation cap 20%; leverage guidance 1x; minimum net R:R 2:1.

## Verified automated checks
- Python/Termux CI run 44291060801: SUCCESS; 221 passed, 4 subtests passed; dependency consistency, minimal synchronous Termux CCXT profile, Widget shell syntax/installer preservation, and Python compilation passed.
- Duplicate CI run 44291070721: SUCCESS on the same candidate code.
- CI run 44290166008: SUCCESS on code head 3aa29bf61d934ca480915c64b910f2989aec617c (221 passed, 4 subtests passed).
- The old historical workflow 44290154788 was cancelled by the concurrency policy; it is superseded and must not be treated as a failure.
- Replacement 365-day historical workflow 44291060559: SUCCESS on documentation-only descendant 853d758e3ea75ade96cd2bfdaad66dccd88cce61; the Python research code is equivalent to 3aa29bf.
- Core source static review found no Spot references in SI_AI_smc.py or si_ai_scanner.py and no create_order/cancel_order/set_leverage/private/balance calls in those files.

## Completed changes
- Checksum-verified Binance Vision monthly archive loader for USD-M OHLCV, mark-price candles and funding-rate audit files.
- Daily markPriceKlines archive fallback repairs identified missing 1h mark-price candles; no interpolation or synthetic candles are used.
- Tests cover checksum validation, path traversal, CSV parsing, symbol validation and daily archive gap repair.
- Conservative intratrade mark-to-market drawdown uses timestamp-aligned mark-price OHLC; intrabar ordering is a conservative bound.
- Chronological training and walk-forward folds slice mark-price arrays to match their OHLCV prefixes.
- Mark-price timestamps must exactly align; mismatch fails closed.
- Funding settlement ambiguity for open, intrabar and close exits is aligned with funding_data.py rules.
- Profitability gate cannot PASS with realized-only drawdown.
- Termux runbook corrected to use binance_vision_backtest.py and explicitly state funding is audit-only, not applied to P&L.

## 365-day historical validation — completed 2026-11-18
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
- Positive individual OOS results do not persist consistently in walk-forward; no symbol is certified profitable.

## Certification blockers — do not claim profitability
1. Binance Vision funding-rate archives do not include exact event-specific settlement markPrice. Rates are archived for audit but not applied to P&L.
2. Timestamp-matched historical maintenance-margin tier snapshots are unavailable; historical liquidation events are not simulated.
3. Mark-price OHLC does not replace exact intrabar liquidation sequencing.
4. The ten symbols use independent 100-USDT reference equity; no shared-wallet portfolio simulation exists.
5. Trade sample size is insufficient: 2–8 OOS trades per symbol and 0–6 trades per walk-forward fold.
6. Android/Termux runtime, live public-data connectivity and Android notification delivery have not been tested on the user's phone.
7. Historical results do not guarantee future performance.

## Exact next steps
1. Continue read-only strategy/backtest audit without changing parameters based on OOS results; inspect signal scarcity, train/OOS split integrity, walk-forward aggregation, trade execution assumptions, and risk sizing.
2. Extend the historical window toward the runner's supported 730-day maximum to seek a larger independent sample; preserve chronological OOS and walk-forward separation. Do not lower evidence thresholds just to obtain a PASS.
3. Investigate a verifiable source for exact historical funding settlement mark prices and timestamp-matched maintenance-margin tier snapshots. If unavailable, keep the gate fail-closed.
4. Build and test a shared-wallet multi-symbol portfolio simulator before making portfolio-level claims.
5. Rerun full CI and historical research after any code change; update this checkpoint with exact commit, run IDs, artifact digest and observed metrics.
6. Only after remote code/research review, prepare one final isolated Termux deployment/verification step. Do not overwrite the existing ~/SI-AI_FINAL checkout.
7. Keep PR #17 draft/unmerged until the user explicitly approves integration.

No live trading is enabled. No automatic orders are placed.
