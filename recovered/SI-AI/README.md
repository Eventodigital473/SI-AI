# SI-AI

SI-AI is a market-analysis and signal-generation project. It uses public Binance market data through `ccxt`, dynamically discovers eligible USDT spot and USD-M perpetual markets, analyzes selected coins across configured timeframes, and exposes a Flask API plus a Termux scanner.

## Dynamic coin universe

- Discovers each market independently from Binance's active USDT-quoted spot and linear USD-M perpetual markets.
- Selects up to 100 coins per market, with a 15-coin minimum required before the scanner will scan that market. The target universe size is 50.
- Ranks candidates by 24-hour quote volume; minimum quote-volume filters are 5 million USDT for spot and 10 million USDT for futures.
- Rejects markets with a spread above 0.15%, missing bid/ask/volume data, inactive market metadata, stablecoin base assets, wrapped assets, and leveraged-token naming patterns.
- SOL, BNB, BTC, and ETH are prioritized only if they pass the same eligibility filters.
- Refreshes the universe every 15 minutes. A failed refresh preserves the last-known-good list; a market with fewer than 15 eligible coins is skipped rather than padded with unqualified symbols.
- The `/api/config` endpoint reports selected symbols by market, eligibility status, and filter settings.

These are initial configurable screening thresholds, not a guarantee of liquidity or profitable execution. Public market data is used only; no private keys or order endpoints are required.

## Safety model

- Signal provider only: this project is intended to report signals for manual review.
- It must not place Binance orders automatically.
- Risk values are paper estimates based on the constants in `SI_AI_smc.py`, not account-specific balances or exchange-confirmed liquidation calculations.
- Review all signals independently before making any trading decision.

## Project files

- `SI_AI_smc.py` — market discovery, public market data, indicators, SMC analysis, and paper risk calculations.
- `si_ai_scanner.py` — multi-timeframe scanner and Termux notifications.
- `main.py` — Flask API.
- `market.py`, `smc.py` — additional source modules retained from the supplied project.
- `test_smc_risk.py`, `test_main_api.py`, `test_dynamic_universe.py` — risk, API, and dynamic-universe tests.

## Dependencies

Install with:

```bash
python -m pip install -r requirements.txt
```

## Tests

```bash
python -m pytest -q
```

The supplied archive was syntax-compiled successfully during packaging. Full test execution still needs the dependencies above installed.

## Secrets

Do not commit Binance API keys, Telegram tokens, passwords, `.env` files, or private account data. This package does not include runtime state, logs, or historical backup files.
