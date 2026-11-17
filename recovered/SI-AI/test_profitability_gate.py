import unittest

from profitability_gate import evaluate_profitability_evidence


def reports():
    oos = {
        "trade_count": 120, "net_pnl_usdt": 80.0, "expectancy_usdt": 0.66,
        "profit_factor": 1.35, "max_drawdown_percent": 8.0,
    }
    wf = {"folds": [
        {"trade_count": 25, "net_pnl_usdt": 20.0},
        {"trade_count": 24, "net_pnl_usdt": 15.0},
        {"trade_count": 30, "net_pnl_usdt": 18.0},
    ]}
    return {"out_of_sample": oos, "assumptions": {
        "historical_funding_series_included": True,
        "funding_mark_price_exact": True,
        "liquidation_modelled": True,
    }}, wf


class ProfitabilityGateTests(unittest.TestCase):
    def test_complete_futures_evidence_can_pass(self):
        oos, wf = reports()
        result = evaluate_profitability_evidence(oos, wf, market="FUTURES")
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["automatic_orders"])

    def test_futures_fails_closed_without_funding_and_liquidation(self):
        oos, wf = reports()
        oos["assumptions"] = {}
        result = evaluate_profitability_evidence(oos, wf, market="FUTURES")
        self.assertEqual(result["status"], "INCONCLUSIVE")

    def test_funding_rates_without_exact_mark_price_remain_inconclusive(self):
        oos, wf = reports()
        oos["assumptions"]["funding_mark_price_exact"] = False
        result = evaluate_profitability_evidence(oos, wf, market="FUTURES")
        self.assertEqual(result["status"], "INCONCLUSIVE")
        check = next(item for item in result["checks"] if item["name"] == "funding_mark_price")
        self.assertEqual(check["status"], "INCONCLUSIVE")

    def test_funding_settlement_boundary_ambiguity_blocks_certification(self):
        oos, wf = reports()
        oos["assumptions"]["funding_settlement_boundary_ambiguities"] = 1
        result = evaluate_profitability_evidence(oos, wf, market="FUTURES")
        self.assertEqual(result["status"], "INCONCLUSIVE")
        check = next(
            item for item in result["checks"]
            if item["name"] == "funding_settlement_boundary_ordering"
        )
        self.assertEqual(check["status"], "INCONCLUSIVE")

    def test_walk_forward_funding_boundary_ambiguity_blocks_certification(self):
        oos, wf = reports()
        wf["folds"][1]["funding_settlement_boundary_ambiguities"] = 1
        result = evaluate_profitability_evidence(oos, wf, market="FUTURES")
        self.assertEqual(result["status"], "INCONCLUSIVE")

    def test_insufficient_trades_is_inconclusive(self):
        oos, wf = reports()
        oos["out_of_sample"]["trade_count"] = 10
        result = evaluate_profitability_evidence(oos, wf, market="FUTURES")
        self.assertEqual(result["status"], "INCONCLUSIVE")

    def test_negative_oos_pnl_fails(self):
        oos, wf = reports()
        oos["out_of_sample"]["net_pnl_usdt"] = -1
        result = evaluate_profitability_evidence(oos, wf, market="FUTURES")
        self.assertEqual(result["status"], "FAIL")

    def test_missing_metrics_never_pass(self):
        result = evaluate_profitability_evidence(
            {"out_of_sample": {}}, {"folds": []}, market="FUTURES"
        )
        self.assertNotEqual(result["status"], "PASS")

    def test_missing_fold_pnl_is_inconclusive_not_false_failure(self):
        oos, wf = reports()
        wf["folds"][0]["net_pnl_usdt"] = None
        result = evaluate_profitability_evidence(oos, wf, market="FUTURES")
        self.assertEqual(result["status"], "INCONCLUSIVE")

    def test_invalid_market_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_profitability_evidence({}, {}, market="MARGIN")


if __name__ == "__main__":
    unittest.main()
