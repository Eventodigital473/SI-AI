# SI-AI

SI-AI is a market-analysis and signal-generation project. It uses public Binance market data through `ccxt`, analyzes BTC/USDT and ETH/USDT across configured timeframes, and exposes a Flask API plus a Termux scanner.

## Safety model

- Signal provider only: this project is intended to report signals for manual review.
- It must not place Binance orders automatically.
- Risk values are paper estimates based on the constants in `SI_AI_smc.py`, not account-specific balances or exchange-confirmed liquidation calculations.
- Review all signals independently before making any trading decision.

## Project files

- `SI_AI_smc.py` — market data, indicators, SMC analysis, and paper risk calculations.
- `si_ai_scanner.py` — multi-timeframe scanner and Termux notifications.
- `main.py` — Flask API.
- `market.py`, `smc.py` — additional source modules retained from the supplied project.
- `test_smc_risk.py`, `test_main_api.py` — risk and API tests.

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
