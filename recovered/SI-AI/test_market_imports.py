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


if __name__ == "__main__":
    unittest.main()
