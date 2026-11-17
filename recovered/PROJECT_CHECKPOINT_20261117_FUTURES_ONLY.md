# SI-AI Futures-only Migration Checkpoint — 2026-11-17

## Active branch and review
- Repository: `Eventodigital473/SI-AI`
- Branch: `feature/futures-only-backtesting`
- Draft PR: https://github.com/Eventodigital473/SI-AI/pull/3
- PR base: `fix/futures-bookticker-normalization-2026-11-17`
- Latest head: `28c754100e2f6838a5123615392eb602e8f973f4`
- Existing `main`, PR #1, and PR #2 have not been merged or rewritten by this migration.

## Completed migration
- Active exchange universe is Binance USD-M USDT perpetual Futures only.
- Spot exchange construction, discovery, scanner support, API market selection, historical-data ingestion, backtest market mode, and Spot-only notification/exit handling have been removed.
- Spot-only public portfolio runner, portfolio simulator, their tests, and the Spot historical validation workflow have been deleted.
- Legacy `market.py` now uses the Binance USD-M Futures public market.
- API rejects `market=SPOT`.
- Historical OHLCV ingestion and CLI accept Futures only.
- Futures-only public historical runner added: `run_public_futures_backtest.py`.
- README and handoff rewritten for Futures-only operation.
- Earlier Spot checkpoint documents are retained only as archived audit history, explicitly marked as non-active.

## Preserved policy
- Public data only; no API keys or private endpoints.
- Signal-only; manual trade execution by user.
- No automatic order placement, cancellation, amendment, or leverage-setting.
- Reference wallet 100 USDT, 0.5% risk per trade, 20% margin allocation cap, conservative 1x Futures leverage.
- 15m / 1h / 4h / 1d multi-timeframe analysis.
- Futures universe: 10M USDT minimum quote volume, 0.15% maximum midpoint-relative spread, target 50, minimum 15, hard maximum 100.

## CI evidence
Latest PR workflow: https://github.com/Eventodigital473/SI-AI/actions/runs/44147729908
- Dependency consistency: PASS (`pip check`, no broken requirements).
- Python compilation: PASS (`compileall`).
- Full automated suite: **112 passed, 4 subtests passed, 0 failures**.
- An earlier run had one test-only assertion failure because a temporary directory was checked after cleanup; the assertion was corrected and the complete suite passed on rerun.

## Backtesting command
From the project directory:

```bash
python run_public_futures_backtest.py --days 180 --symbol BTC/USDT
```

Multiple symbols can be supplied by repeating `--symbol`:

```bash
python run_public_futures_backtest.py --days 180 --symbol BTC/USDT --symbol ETH/USDT --symbol SOL/USDT
```

History window is 120–730 days. Each symbol is currently evaluated with its own reference equity; this is not a shared-wallet portfolio replay. Data is stored in git-ignored `data/historical/` and reports in `data/reports/`.

## Remaining blockers / exact next step
1. Clone or safely sync this branch into a separate Termux directory without overwriting `~/SI-AI_FINAL` or any existing local state.
2. On-device run: `python -m pip check`, `python -m compileall -q .`, and `python -m pytest -q`.
3. Run `python si_ai_scanner.py --once --dry-run`; inspect Futures bookTicker matching, valid bid/ask, spread-qualified and selected counts.
4. Verify actual Android notifications with Termux:API on the phone.
5. Execute a real historical Futures backtest and inspect dataset hashes, chronological holdout, walk-forward output, and report assumptions.
6. Do not claim Futures profitability certification: timestamped historical Binance funding and exchange-specific maintenance-margin/liquidation modelling are still missing. The profitability gate must remain INCONCLUSIVE until both are implemented and validated.

## Release status
- Futures-only code migration: implemented.
- GitHub CI: passed.
- PR #3: open, draft, unmerged.
- Termux/device smoke test: pending.
- Real Futures historical backtest: pending.
- Futures profitability certification: INCONCLUSIVE.
