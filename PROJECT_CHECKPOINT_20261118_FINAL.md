# SI-AI Resume Checkpoint — 2026-11-18 (latest verified CI; 730-day research pending)

## Candidate and safety
- Repository: Eventodigital473/SI-AI
- Candidate branch: `fix/scanner-risk-audit-2026-11-18`
- Latest code commit covered by passing CI: `8db3277a0d80c3981ebced5f096c70e0a79ba475`. Later checkpoint/PR-description updates are documentation-only.
- Latest candidate commit `8db3277a` includes the strict archive coverage and test fixture alignment changes; see CI run below.
- Draft PR: https://github.com/Eventodigital473/SI-AI/pull/17
- PR #17 is open, draft, mergeable and unmerged. Do not merge without explicit user approval.
- Futures-only; Spot excluded from the active scanner/backtest files.
- Signal/notification provider only. No automatic orders, private account endpoints or balance fetching.
- Reference equity 100 USDT; per-trade risk 0.5% (0.50 USDT); margin allocation cap 20%; leverage guidance 1x; minimum net R:R 2:1.

## Latest verified automated checks
- Latest CI on the latest code commit (documentation-only checkpoint updates followed): https://github.com/Eventodigital473/SI-AI/actions/runs/44342780258 — SUCCESS.
- Exact pytest output: **231 passed, 8 subtests passed in 2.15 seconds**.
- Dependency consistency passed; minimal synchronous Termux CCXT profile passed with CCXT 4.5.93; Termux Widget shell syntax and installer preservation passed; Python compilation passed.
- Previous CI run: https://github.com/Eventodigital473/SI-AI/actions/runs/44342174543 — SUCCESS, same 231 passed and 8 subtests.
- 730-day historical workflow: https://github.com/Eventodigital473/SI-AI/actions/runs/44341693703 — last checked 2026-11-18 16:04 UTC, still IN_PROGRESS. Dependency installation, compile, and full automated tests passed; 730-day checksum-verified Binance Vision backtest step remained in progress. No artifact was available yet. Its job-log endpoint returned NOT_FOUND while running, so no further output or completion is claimed.
- Earlier intermediate CI failures on commits `6c80f59`, `ceedcd6`, `a5bb89c`, and `ddda39f` were due to synthetic fixtures with non-UTC-aligned candle timestamps after strict coverage validation. Fixtures were corrected; later CI on `d083ec0` and `395a943` passed.
- Historical 365-day baseline run: https://github.com/Eventodigital473/SI-AI/actions/runs/44291060559 — SUCCESS.
- Core scanner static review found no Spot references in `SI_AI_smc.py` or `si_ai_scanner.py` and no `create_order`, `cancel_order`, `set_leverage`, private account, or balance calls in those core files.

## Completed changes in latest audit
1. **Profitability gate fail-open fix:** all supplied walk-forward folds are now evaluated; malformed fold entries make evidence INCONCLUSIVE. Regression tests cover a later losing fold and malformed extra fold.
2. **Binance Vision archive coverage:** requested start/end candle coverage and UTC timeframe alignment are required, in addition to checksum validation and internal continuity. Missing first/last candles cannot pass.
3. **Public OHLCV and mark-price coverage:** shared full-window coverage validation is used by historical OHLCV and mark-price downloads, saved datasets and loaded datasets. Edge gaps fail closed.
4. **Regression tests:** added edge-gap, malformed-fold, and UTC-boundary tests; synthetic fixture timestamps were aligned to real Binance UTC candle boundaries.
5. **Historical research window:** GitHub historical workflow extended from 365 to 730 days for BTC, ETH, BNB, XRP, ADA, DOGE, LINK, AVAX, DOT and SOL.

## Resume update — 2026-11-18 16:05 UTC

- Re-read the current candidate's funding path and backtest integration.
- Confirmed the public funding downloader validates the raw Binance event symbol, funding timestamp/rate agreement, and event-specific settlement markPrice; the historical backtest applies timestamped funding cashflows when this verified dataset is supplied.
- Confirmed the Vision archive workflow intentionally does not pass monthly funding-rate CSV values into P&L because those CSVs do not include exact event markPrice. It records this as an explicit limitation rather than silently substituting candle close.
- Confirmed funding settlement ambiguity counts propagate from trade records into OOS and every walk-forward fold; the profitability gate requires zero ambiguities.
- Latest test output and candidate head are recorded above. No Termux device run has been performed in this session.
- The 730-day workflow remains in progress at the backtest step; do not assume it succeeded or failed until GitHub reports a terminal state and artifacts are inspected.

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


## Resume update — 2026-11-18 16:09 UTC

- Latest code commit: `9528aa872453d90699a2783c6db4fb1b1f49585e`.
- Fixed Binance Vision CSV parsing: only documented `open_time` and `calc_time` headers are skipped; an arbitrary malformed first row now raises an error rather than silently dropping the first candle/funding record.
- Added regression test for malformed first archive data row.
- Latest full PR CI: [44343719061](https://github.com/Eventodigital473/SI-AI/actions/runs/44343719061) — SUCCESS; **232 passed, 8 subtests passed in 1.42s**. Dependency consistency, minimal synchronous Termux CCXT profile, Widget shell syntax and Python compilation also passed.
- Latest 730-day historical validation for this exact code commit: [44343707734](https://github.com/Eventodigital473/SI-AI/actions/runs/44343707734) — still running at 16:09 UTC. Dependency, compile and full test stages passed; the archive backtest step is in progress. No report/artifact or historical outcome is claimed yet.
- Previous 730-day attempts on older commits were cancelled when newer candidate commits superseded them; do not use their partial state as a completed result.
- Workflow now runs on integration PR changes as well as pushes/manual dispatch.
- PR #17 remains draft and unmerged. No automatic order placement or private account API has been enabled.
- Next exact step: wait for run 44343707734 to finish, inspect its report and dataset artifacts, then fix any archive/data/backtest failures. Do not certify profitability if funding or historical liquidation evidence remains incomplete.

## Resume update — 2026-11-18 16:11 UTC

- Current PR head: `e490e0b5cfd0ec6682fc779bf65f92adb16e7dff`; this commit updates the PR description/checkpoint only after the last tested code commit `9528aa872453d90699a2783c6db4fb1b1f49585e`.
- Latest CI on current PR head: [44343916874](https://github.com/Eventodigital473/SI-AI/actions/runs/44343916874) — SUCCESS. The complete job passed dependency consistency, synchronous Termux CCXT profile, Termux Widget shell checks, compilation and the full test suite. The exact test count remains 232 passed, 8 subtests from the immediately preceding code commit's test output.
- Current-head 730-day PR validation: [44343916868](https://github.com/Eventodigital473/SI-AI/actions/runs/44343916868) — in progress. Setup, dependency consistency, compilation and full automated tests have passed; 730-day Binance Vision archive backtest is still in progress. No artifacts are available yet.
- Earlier same-code push validation [44343707734](https://github.com/Eventodigital473/SI-AI/actions/runs/44343707734) also remains reported in progress but is stale; prefer current PR run 44343916868 for candidate validation.
- GitHub job-log download endpoint returned 404 for the active job; job status and step summaries remain accessible. This is not evidence of a backtest failure.
- PR #17 remains open, draft and unmerged. No live order placement.
- Exact next step: poll 44343916868; once complete, fetch artifacts, inspect checksums and all per-symbol reports. If it remains in progress unusually long, investigate archive download/runner timeout rather than claiming success.


## Resume update — 2026-11-19: 730-day validation completed and independently audited

- Candidate branch: `fix/scanner-risk-audit-2026-11-18`; PR #17 remains open, draft, mergeable and unmerged. Do not merge without explicit user approval.
- Current branch head observed: `d0d2cb995f4b26cea5fe078cf5f7cba6f6691fc2` (checkpoint/PR status update after code changes). Latest PR-head workflows:
  - Python tests run [44344222581](https://github.com/Eventodigital473/SI-AI/actions/runs/44344222581): SUCCESS.
  - 730-day Futures historical validation [44344222453](https://github.com/Eventodigital473/SI-AI/actions/runs/44344222453): SUCCESS.
- Exact latest test log: **232 passed, 8 subtests passed in 2.18s**. Dependency consistency, compilation, and the 730-day historical job all completed successfully.
- Downloaded validation artifact: `si-ai-futures-validation-44344222453`, 71 JSON files, 21.8 MB. GitHub artifact digest: `sha256:e0846b4b30a4fda934faf041ba2af1109196e78f99452df8f9ad51769265c64d`; independently downloaded ZIP SHA-256 matched exactly. ZIP CRC passed.
- Independent artifact audit: all 10 per-symbol reports parsed; report schema, OOS trade counts, three walk-forward folds per symbol, fold trade counts and `automatic_orders=false` were cross-checked. All 50 historical candle datasets with embedded candles passed their declared SHA-256 and candle-count checks.
- Actual period: 2024-11-01 through 2026-11-01 UTC (730 days). OOS trades: 117 total across 10 independently sized symbol runs; walk-forward trades: 170 total. OOS profitable symbols: 4/10; walk-forward profitable symbols: 5/10. All 10 per-symbol profitability gates are FAIL; overall certification is INCONCLUSIVE.
- Per-symbol OOS trade counts are only 8–15; walk-forward folds contain only 2–9 trades each. Do not weaken the gate thresholds to force PASS.
- The 730-day Vision archive stores funding-rate history but does not apply it to P&L because archive records lack the exact event-specific settlement markPrice. Historical liquidation is not modelled because timestamp-matched maintenance tiers and exact intrabar liquidation sequencing are unavailable. The archive summary explicitly records no shared-wallet portfolio simulation.
- Additional exploratory-only shared-wallet diagnostic was run against the downloaded OOS trades and matching mark-price OHLC. Under the 100 USDT reference wallet, 0.5% per-trade risk, 20% aggregate notional cap, 1x leverage, dynamic sizing, conservative adverse mark-price MTM, and no funding/liquidation, 104 of 117 candidate entries were admitted; 13 were skipped for capacity. Realized net P&L was approximately -1.9886 USDT; conservative mark-price max drawdown approximately 4.7333%. This is a research diagnostic script, not an integrated or CI-certified production simulator; do not use it as a final portfolio report.
- Exploratory shared-wallet walk-forward fold diagnostics: fold 1 +5.0965 USDT; fold 2 -0.4995 USDT; fold 3 -1.5395 USDT, under the same simplified assumptions. Only 1/3 folds positive. These results further do not support profitability certification.
- Termux runbook and widget scripts were inspected. The user has already cloned to `~/SI-AI_FINAL_VALIDATION` and installed the isolated Termux dependencies through CCXT 4.5.93; do not ask them to clone or reinstall. Device preflight, Python 3.14 runtime, live Binance public-data access, Android Termux:API companion/permissions, notification behavior and phone-side dry-run remain unverified.
- No changes were made to main, the integration branch, or the user's existing `~/SI-AI_FINAL` project. No private Binance credentials, account endpoints, or automatic orders were used.

## Exact next engineering steps

1. Implement a formal, deterministic shared-wallet portfolio backtest in the candidate branch. It must replay all symbols on one chronological event timeline, use shared equity and aggregate margin allocation, size from the shared 0.5% risk budget, define simultaneous entry/exit ordering, prevent double-counting, and calculate portfolio mark-price drawdown. Add regression tests for overlapping positions, simultaneous entries/exits, capacity rejection/scaling, equity changes, and missing mark candles.
2. Integrate exact timestamped Binance funding events with their event-specific settlement markPrice over the full historical period; verify pagination, event completeness, boundary handling and API retention. Never substitute OHLCV close for settlement markPrice. If the endpoint cannot provide full history, retain the limitation and block certification.
3. Continue fail-closed liquidation research. Do not claim liquidation safety from mark OHLC alone; historical maintenance tiers and intrabar sequencing limitations must be explicit.
4. Re-run full CI and 730-day research on the exact updated code commit. Keep all existing profitability thresholds; evaluate portfolio OOS and every walk-forward fold.
5. Only after remote code and research review, run the already-installed isolated Termux validation path. The user should not receive another setup/install command. Prepare one final command sequence for local compile/tests, offline preflight, public Futures dry-run, and a separate notification test only after confirming the Termux:API companion app.
6. Keep PR #17 draft/unmerged and automatic orders disabled. Do not label the project profitability-certified or ready for live trading.

No live trading is enabled. No automatic orders are placed.


## Resume update — 2026-11-19: shared-wallet engine and public API access finding

- Latest branch head: `0ea57105628bf8d24ebc85a43ca9d8028f009b41`. PR #17 remains open, draft, mergeable and unmerged.
- Added `recovered/SI-AI/shared_wallet_backtest.py`: deterministic shared-equity sizing, aggregate notional admission cap, pro-rata simultaneous entries, mark-price adverse OHLC drawdown, fail-closed data checks, atomic JSON output, and portfolio-level OOS/three-fold reporting.
- Added `recovered/SI-AI/test_shared_wallet_backtest.py`: 12 regression tests covering shared cap, simultaneous allocation, open/intrabar exit ordering, ambiguous same-symbol boundaries, missing mark candles, long/short adverse marks, and accounting.
- Shared-wallet engine was run locally against the previously downloaded 730-day artifact. It validates the mark-price dataset manifest and SHA-256 hashes, uses the report's exact 0.5% risk / 20% margin / 1x leverage / fee / slippage assumptions, and explicitly excludes funding and liquidation. The initial exploratory Vision OOS result was 104 executed / 13 capacity-skipped from 117 candidates, net P&L about -1.9886 USDT, adverse mark-price max drawdown about 4.7333%. Walk-forward folds were approximately +5.0965, -0.4995, and -1.5395 USDT. These are research diagnostics, not certification.
- Latest Python CI run [44402897751](https://github.com/Eventodigital473/SI-AI/actions/runs/44402897751): **244 passed, 8 subtests passed**; dependency consistency, minimal Termux CCXT profile, widget shell checks, and compilation passed.
- Latest 730-day Vision + shared-wallet workflow [44402897767](https://github.com/Eventodigital473/SI-AI/actions/runs/44402897767) is still in progress at this checkpoint. Inspect its final shared-wallet step and artifact before claiming completion.
- A separate attempt to validate exact settlement funding through Binance USD-M Futures REST was blocked before data retrieval: GitHub-hosted runner received HTTP **451** from `https://fapi.binance.com/fapi/v1/exchangeInfo`, with Binance response stating service unavailable from a restricted location. This is an external access/eligibility restriction, not a Python test failure. No VPN, proxy, alternate routing or other restriction bypass was attempted.
- Removed the auto-triggering GitHub public-Futures workflow after the 451 finding to avoid repeated prohibited/pointless requests. The existing `run_public_futures_backtest.py` and exact funding parser remain in the repository, but actual public API retrieval is unverified from the GitHub runner. The user’s Termux access is unknown and must be tested only through the normal official endpoint; if it returns 451, stop and do not try to circumvent it.
- The Binance Vision 730-day archive workflow remains the available historical dataset source. Its funding archive has rates but not exact settlement markPrice, so it cannot certify funding cashflows. Historical liquidation remains unmodelled.
- The user’s Termux folder and venv already exist at `~/SI-AI_FINAL_VALIDATION/recovered/SI-AI/.venv`; do not request another clone or dependency installation. Final phone-side compile/tests, preflight, and one public Futures dry-run remain pending. No automatic orders are enabled.

## Exact next step
1. Wait for workflow `44402897767` and independently inspect its shared-wallet JSON artifact and job logs.
2. Keep PR #17 draft/unmerged. Keep profitability certification blocked/inconclusive; do not tune thresholds to force a pass.
3. Only after the above, give the user one reviewed Termux update-and-validation command sequence using the existing clone and venv. The phone-side public API dry-run must stop on HTTP 451; do not propose a VPN/proxy workaround.


## Correction and final validation status — 2026-11-18 21:43 UTC

- Current branch head is now `d5ba05b8c3c7709f77c6baa87a0a92678857d8cd`; PR #17 remains open, draft, mergeable and unmerged.
- Scanner operational fail-closed fix committed:
  - HTTP 451 during universe refresh or candle retrieval now stops the cycle immediately; it does not continue across the remaining symbols or attempt a regional restriction bypass.
  - A cycle with zero successfully analysed symbols now exits as an error.
  - A dry-run must complete at least the configured minimum number of symbols before it can report success.
  - Live cycles with partial but non-zero coverage log an explicit warning.
- Added three scanner-cycle regression tests. Latest test workflow runs [44404257888](https://github.com/Eventodigital473/SI-AI/actions/runs/44404257888) and [44404250810](https://github.com/Eventodigital473/SI-AI/actions/runs/44404250810) completed successfully: **247 passed, 8 subtests passed**. Dependency checks, pinned CCXT 4.5.93 synchronous import profile, Termux Widget shell checks, and Python compilation all passed.
- The expensive 730-day Vision workflow is now manual-dispatch only to prevent every scanner-only PR update from re-downloading the full historical archive. Two redundant reruns [44404258273](https://github.com/Eventodigital473/SI-AI/actions/runs/44404258273) and [44404249848](https://github.com/Eventodigital473/SI-AI/actions/runs/44404249848) were already queued before that trigger change and were still in progress at this checkpoint.
- The previous completed 730-day Vision dataset run [44344222453](https://github.com/Eventodigital473/SI-AI/actions/runs/44344222453) remains the source for the local shared-wallet integration test. The updated shared-wallet engine was run against that artifact locally; exact report manifests, mark-price SHA-256, report risk policy and walk-forward windows validated. The portfolio diagnostic remains negative and not profitability-certified; funding and liquidation remain excluded.
- The attempted exact-funding public API job was removed after Binance HTTP 451 from the GitHub runner. Do not use VPN/proxy or attempt to bypass. The Termux device's normal API access is still unknown.
- Existing Termux clone and venv remain at `~/SI-AI_FINAL_VALIDATION/recovered/SI-AI/.venv`. No new clone or package install is needed. The final device check must use `git pull --ff-only`, compile, pytest, preflight and one dry-run. If the normal Binance endpoint returns 451, stop; do not start continuous scanning.

## Remaining exact next step
Run the single final Termux update/validation sequence only after confirming the latest source is on branch head `d5ba05b8c3c7709f77c6baa87a0a92678857d8cd`. If the phone-side dry-run passes and notification companion app is confirmed, explain foreground start/stop. Do not call SI-AI profitability-certified or recommend live execution.
