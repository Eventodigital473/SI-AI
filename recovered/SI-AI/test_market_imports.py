import importlib
import unittest
from unittest.mock import patch

import ccxt


class ImportSafetyTests(unittest.TestCase):
    def test_importing_market_module_does_not_make_network_request(self):
        with patch.object(
            ccxt.binance,
            "fetch_ticker",
            side_effect=AssertionError("network request during import"),
        ):
            module = importlib.import_module("market")
            importlib.reload(module)



    def test_legacy_smc_module_uses_futures_client_not_spot(self):
        import SI_AI_smc
        with patch.object(
            ccxt,
            "binance",
            side_effect=AssertionError("legacy Spot client must never be created"),
        ):
            module = importlib.import_module("smc")
            importlib.reload(module)
        self.assertIs(module.exchange, SI_AI_smc.EXCHANGES["FUTURES"])

    def test_legacy_smc_entrypoints_delegate_to_futures_engine(self):
        import SI_AI_smc
        module = importlib.import_module("smc")
        with patch.object(
            SI_AI_smc, "get_candles", return_value=[[1, 1, 1, 1, 1, 1]]
        ) as mocked:
            result = module.get_candles("BTC/USDT", "1h")
        self.assertEqual(result, [[1, 1, 1, 1, 1, 1]])
        mocked.assert_called_once_with("FUTURES", "BTC/USDT", "1h")

if __name__ == "__main__":
    unittest.main()
