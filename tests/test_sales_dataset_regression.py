"""Regression tests for the sales dataset used in the product demo."""

import os
import tempfile
import unittest

from app.services import data_loader, llm_analyst


class SalesDatasetRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = os.path.join(os.path.dirname(__file__), "fixtures", "sample_sales_dataset.csv")
        cls.dataset = data_loader.load_dataset("sample_sales_dataset.csv", source)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.dataset.con.close()
        except Exception:
            pass

    def test_region_alias_maps_to_geographic_team_column(self):
        result = llm_analyst._try_grouped_query(
            self.dataset, "show me revenue across regions"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "local_grouped_analysis")
        self.assertEqual(len(result["rows"]), 4)
        south = next(row for row in result["rows"] if row["team"] == "South")
        self.assertAlmostEqual(float(south["value"]), 642500.0)

    def test_revenue_by_channel_uses_totals(self):
        result = llm_analyst._try_grouped_query(
            self.dataset, "show revenue by channel"
        )
        self.assertIsNotNone(result)
        self.assertEqual(len(result["rows"]), 4)
        email = next(row for row in result["rows"] if row["channel"] == "Email")
        self.assertAlmostEqual(float(email["value"]), 436000.0)

    def test_executive_insight_uses_totals_and_business_context(self):
        result = llm_analyst._try_main_insight_query(
            self.dataset, "What is the main insight?"
        )
        self.assertIsNotNone(result)
        answer = result["answer"]
        self.assertIn("1,365,500.00", answer)
        self.assertIn("1,140,400.00", answer)
        self.assertIn("506.62%", answer)
        self.assertIn("South", answer)
        self.assertIn("Diwali Mega Sale", answer)
        self.assertIn("Festive Email Push", answer)
        self.assertNotIn("summary of the numeric columns", answer.lower())

    def test_profit_and_roi_are_calculated_from_totals(self):
        profit = llm_analyst._try_derived_metric_query(
            self.dataset, "calculate total profit"
        )
        roi = llm_analyst._try_derived_metric_query(
            self.dataset, "calculate ROI"
        )
        self.assertAlmostEqual(float(profit["rows"][0]["value"]), 1140400.0)
        self.assertAlmostEqual(float(roi["rows"][0]["value"]), 506.6192803198578, places=4)

    def test_conversion_rate_uses_total_conversions_over_total_leads(self):
        result = llm_analyst._try_derived_metric_query(
            self.dataset, "what is the overall conversion rate?"
        )
        self.assertAlmostEqual(float(result["rows"][0]["value"]), 15.447470817120623, places=4)

    def test_daily_revenue_trend_returns_twenty_days(self):
        result = llm_analyst._try_trend_query(
            self.dataset, "show daily revenue trend"
        )
        self.assertIsNotNone(result)
        self.assertEqual(len(result["rows"]), 20)

    def test_dataset_does_not_claim_a_region_column_exists(self):
        columns = llm_analyst._columns(self.dataset)
        self.assertIn("team", columns)
        self.assertNotIn("region", [column.lower() for column in columns])


if __name__ == "__main__":
    unittest.main()
