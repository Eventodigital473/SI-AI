# SI-AI Recovery Checkpoint — 2026-11-17 (Dynamic-Universe Portfolio Validation)

## Authoritative working branch
- Repository: `Eventodigital473/SI-AI`
- Working branch: `feature/dynamic-coin-universe`
- Checkpoint commit: `af7cc5ccb71398e1d3938275d152feb083bf173b`
- Source/test commit covered by the 92-test run: `3db4d0386a1a80f035a5f5de956700f136c1e133`
- Pull request: #1, still open/draft, targeting `recovery/restore-upload-zip`; do not merge to main until remaining validation gates are complete.
- The project source of truth is `recovered/SI-AI/` on this branch. The earlier Phase B local ZIP from the separate stale workspace is not the authoritative project and must not replace this branch.

## Safety and risk configuration
- Signal provider only; no automatic order placement, cancellation, amendment, or leverage-setting calls.
- Latest confirmed risk assumptions in this branch: 100 USDT reference paper equity, 0.5% risk per trade, 20% maximum notional allocation, 1x Futures leverage ceiling.
- Spot SELL is exit-only; Spot shorts are rejected.
- Public market data only; no API keys or account endpoints.

## Verified engineering work
- Existing GitHub Actions evidence before this continuation: 81 tests + 4 subtests passed.
- Added a shared-equity multi-symbol Spot portfolio replay with one concurrent position; overlapping opportunities are skipped conservatively and each trade is re-sized from the same 100 USDT wallet.
- Historical confluence now uses the same 250 closed candles per timeframe as the live scanner. Auxiliary timeframe history is sliced with bisect, avoiding repeated full-history scans.
- Added portfolio aggregation for chronological OOS trades and each walk-forward fold. Walk-forward fold reports retain trade details for the portfolio gate.
- Added a read-only public Spot data runner, `run_public_spot_portfolio.py`, using the official public market-data-only host `data-api.binance.vision`; the runner restricts CCXT market metadata to Spot and does not call Futures/private endpoints.
- Added exact, gap-free OHLCV window checks so symbols listed after the requested start date or missing candles are skipped rather than creating misaligned OOS/fold windows.
- Added tests for shared-wallet sizing, overlap rejection, Spot long-only handling, portfolio aggregation, and the public-data runner.

## Latest verified CI
- GitHub Actions run `44076193074`: 92 passed, 4 subtests passed.
- This run tested source/test commit `3db4d0386a1a80f035a5f5de956700f136c1e133`.
- No local compatibility shims were used for this GitHub Actions run; dependencies were installed from `requirements.txt`.

## Historical research status
- Earlier single-symbol 180-day BTC/USDT Spot run successfully downloaded and SHA-256-verified 15m/1h/4h/1d data.
- That BTC-only run produced 3 chronological OOS trades and walk-forward fold counts 2/3/0. Profitability gate correctly returned FAIL for insufficient sample; this is not profitability evidence.
- New dynamic-universe portfolio run: GitHub Actions run `44076185055`, in progress at checkpoint update. It targets up to 50 currently eligible Spot symbols over 180 days, requires at least 15 symbols with complete, identically aligned history, validates dataset hashes, and runs the shared-equity portfolio gate.
- The current universe snapshot is applied retrospectively; historical universe membership is not reconstructed, so survivorship bias remains.
- Futures profitability remains INCONCLUSIVE until timestamped historical funding and exchange-specific liquidation/maintenance-margin modelling are included.

## Exact next steps
1. Inspect completion of run `44075697088`; read the portfolio report and download the workflow artifact.
2. Do not lower profitability thresholds to force PASS. If sample count or metrics fail, report the exact reason and keep profitability uncertified.
3. Add any necessary data/engine corrections and rerun the real-dependency GitHub Actions suite.
4. Keep the PR open/draft until historical evidence, paper-trading period, and device checks are complete.
5. Only then prepare one timestamped Termux backup/install command. Preserve all prior backups, runtime state, logs, and user secrets.
6. Verify Android notification permission, sound, and vibration on the physical device. No Termux deployment has yet been performed.

## Historical single-symbol evidence
- Dataset: BTC/USDT Spot, 180 requested days, 17,279 15m / 4,319 1h / 1,079 4h / 179 1d candles.
- Profit factor 1.256, maximum realized drawdown 0.287%, net OOS P&L +0.0739 USDT on 100 USDT, but only 3 OOS trades; gate FAIL due insufficient sample.
- This report is diagnostic only and is superseded by the pending multi-symbol portfolio run for sample-size evaluation.
