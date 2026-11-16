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
