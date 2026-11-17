# SI-AI Project Checkpoint — 2026-11-17 (Portfolio Backtest + Stablecoin Filter)

## Source of truth
- Repository: `Eventodigital473/SI-AI`
- Working branch: `feature/dynamic-coin-universe`
- Latest code commit at checkpoint: `589a6c4b9993258776e18ea1f40fb28e6a56ca29`
- Recovery branch: `recovery/restore-upload-zip`
- Main branch remains untouched.
- PR #1 remains open; do not merge to main until all validation gates are complete.
- Canonical project source is `recovered/SI-AI/` on the feature branch.

## User requirements / safety
- SI-AI is a signal provider only. The user manually executes trades on Binance.
- No automatic Binance order placement, cancellation, amendment, or leverage-setting.
- Use public market data only; do not request API keys or private account endpoints.
- Preserve all existing backups and runtime state. Do not delete files or historical datasets until their purpose and a verified replacement are established.
- Risk assumptions in project: 100 USDT paper reference equity, 0.5% risk budget per trade, 20% notional/margin allocation cap, Futures leverage ceiling 1x.

## Verified source and tests before latest small patch
- Latest completed CI run before current patch: GitHub Actions run `44086170197`, commit `9358080b8a655e96cd37ea38fadfea9116991794`.
- Downloaded JUnit artifact `si-ai-test-evidence-112` and inspected it: **107 tests, 0 failures, 0 errors, 0 skipped**; compile step and test job succeeded.
- The earlier checkpoint's 92-test count is superseded by this exact JUnit evidence.
- These 107 tests apply to commit `9358080...`, not to the subsequent stablecoin-filter patch.

## Historical Spot portfolio backtest — completed evidence
- GitHub Actions run: `44076185055`, source commit `3db4d0386a1a80f035a5f5de956700f136c1e133`, completed successfully.
- Downloaded artifact: `si-ai-public-spot-history-17.zip` (13,633,890 bytes).
- 180-day Binance public Spot history requested for 50 currently eligible symbols.
- 34 symbols had complete, gap-free, aligned history across 15m, 1h, 4h, and 1d; 16 were skipped for incomplete history.
- Every downloaded dataset was SHA-256 checked. Combined dataset SHA-256: `d19a9ba48226275126826df0d1ecf6b5b5d6331f170c4146abc9b3d88446813a`.
- Shared 100 USDT wallet, one open position maximum; 54 overlapping opportunities skipped.
- Chronological out-of-sample: 25 trades; win rate 16%; profit factor 0.35276535; net P&L -4.60920861 USDT; expectancy -0.18436834 USDT/trade; max drawdown 5.76540559%; ending equity 95.39079142 USDT.
- Walk-forward: 45 trades; net P&L -4.52025385 USDT; profit factor 0.63216407; ending equity 95.47974617 USDT.
- Profitability gate: **FAIL**. Do not represent this strategy as profitable or enable live trading based on these results.
- 25 OOS trades are below the policy minimum of 100. Fold 2 and fold 3 are below 20 trades. Survivorship bias remains because today's eligible universe was applied retrospectively; the backtest is diagnostic, not a certification.
- Futures profitability remains inconclusive without timestamped historical funding and exchange-specific liquidation/maintenance-margin modelling.
- No automatic orders were placed.

## Changes made after inspecting the backtest
- Backtest trade ledger included `RLUSD/USDT` and `XUSD/USDT`, which are USD stablecoin base assets and should not be included in the directional coin universe.
- Added RLUSD and XUSD to `EXCLUDED_BASES` in `recovered/SI-AI/SI_AI_smc.py`.
- Added fixture coverage and exclusion assertions for both symbols in `recovered/SI-AI/test_dynamic_universe.py`.
- Code commit: `e796d84d13119b173748c3e4c9bda1c3b4f5be13`.
- Test commit: `589a6c4b9993258776e18ea1f40fb28e6a56ca29`.
- This is a narrow data-universe hygiene fix, not a strategy optimization and not a claim that profitability will improve.

## Current validation in progress
- Dynamic-universe CI run `44088548976` (run #114) for commit `589a6c4...`: in progress at checkpoint time.
- Public Spot historical validation run `44088541205` (run #31) for commit `589a6c4...`: queued at checkpoint time.
- Prior run `44088524969` was cancelled by the newer commit; do not count it as a pass.
- Retrieve both current run results and inspect the new portfolio artifact/report before making further strategy changes.

## Cleanup / deployment
- No files have been deleted. The root ZIP is a preserved source backup; checkpoint files, manifests, workflows, and historical artifacts are evidence or recovery material, not disposable clutter.
- Do not remove the archive, recovery directory, reports, or test files.
- Termux deployment has not been performed or verified. Do not claim device notifications, sound, or vibration are working until checked on the physical Android device.
- Do not modify `main` or merge the draft PR until the code/test/backtest and device-validation gates are complete.

## Exact next steps
1. Check completion of CI run `44088548976`; verify its JUnit count and confirm zero failures.
2. Check completion of historical validation run `44088541205`; inspect the updated summary and artifact after RLUSD/XUSD exclusion.
3. Audit remaining universe candidates and portfolio/backtest assumptions without tuning thresholds to force a PASS.
4. Keep all data and source backups. Only propose deletion after proving a file is redundant and a verified backup exists.
5. Prepare a single timestamped Termux backup/deployment procedure only after the reviewed feature branch passes validation.
6. Run device checks for Android notification permission, sound, and vibration. Keep SI-AI signal-only/manual execution.
