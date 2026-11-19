"""Regression tests for a transaction-style sales dataset.

The fixture deliberately uses the real 1M-row demo schema, not the older
campaign/leads/conversions schema.
"""
import os
import tempfile
import unittest

from app.services import data_loader, llm_analyst
from app.services.agent import AnalystAgent


CSV = """date,region,product,channel,customer_segment,customer_id,salesperson_id,units_sold,unit_price,discount,marketing_spend,customer_rating,returns,revenue,net_revenue,return_rate,profit_margin,profit
2025-01-01,South,Laptop,Online,Consumer,C1,SP1,2,100,0,10,4.5,0,200,200,0,0.20,40
2025-01-02,South,Phone,Retail,Corporate,C2,SP2,1,200,0.1,15,4.0,1,200,180,0.5,0.25,45
2025-01-03,East,Laptop,Online,Consumer,C3,SP3,1,100,0,8,4.2,0,100,100,0,0.20,20
2025-01-04,North,Mouse,Retail,Small Business,C4,SP4,2,20,0,5,3.8,0,40,40,0,0.25,10
2025-01-05,West,Tablet,Wholesale,Corporate,C5,SP5,1,300,0.1,20,4.8,0,300,270,0,0.30,81
2025-01-06,West,Headphones,Online,Consumer,C6,SP6,1,50,0,6,4.0,1,50,0,1,0,0
"""


class RealSalesSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        )
        handle.write(CSV)
        handle.close()
        cls.csv_path = handle.name
        cls.dataset = data_loader.load_dataset("real_sales_schema.csv", cls.csv_path)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.dataset.con.close()
        finally:
            if os.path.exists(cls.csv_path):
                os.unlink(cls.csv_path)

    def test_plural_regions_resolve_to_region_column_and_sum_revenue(self):
        result = llm_analyst._try_grouped_query(
            self.dataset, "show me revenue across regions"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "local_grouped_analysis")
        values = {row["region"]: float(row["value"]) for row in result["rows"]}
        self.assertEqual(values, {"South": 400.0, "West": 350.0, "East": 100.0, "North": 40.0})
        self.assertIn("SUM(", result["sql"])

    def test_agent_plans_region_question_as_grouped_local_analysis(self):
        plan = AnalystAgent(self.dataset).plan("show me revenue across regions")
        self.assertEqual(plan[0].tool, "grouped_analysis")

    def test_main_insight_uses_real_schema_and_weighted_metrics(self):
        result = llm_analyst._try_main_insight_query(
            self.dataset, "What is the main insight?"
        )
        self.assertIsNotNone(result)
        answer = result["answer"]
        self.assertIn("6 transaction records", answer)
        self.assertIn("Gross revenue totals 890.00", answer)
        self.assertIn("Net revenue after returns/adjustments totals 790.00", answer)
        self.assertIn("Recorded profit totals 196.00", answer)
        self.assertIn("Weighted profit margin is 24.81%", answer)
        self.assertIn("Return rate by units is 25.00%", answer)
        self.assertIn("Leading region by revenue is South at 400.00", answer)
        self.assertNotIn("conversion rate", answer.lower())
        self.assertNotIn("campaign", answer.lower())

    def test_main_insight_does_not_treat_marketing_spend_as_total_cost(self):
        result = llm_analyst._try_main_insight_query(
            self.dataset, "What is the main insight?"
        )
        self.assertNotIn("total_cost", result["rows"][0])
        self.assertIn("total_marketing_spend", result["rows"][0])

    def test_agent_routes_main_insight_to_deterministic_summary_tool(self):
        plan = AnalystAgent(self.dataset).plan("What is the main insight?")
        self.assertEqual(plan[0].tool, "main_insight")

    def test_agent_executes_main_insight_without_generic_model_fallback(self):
        result = AnalystAgent(self.dataset).run("What is the main insight?")
        self.assertEqual(result["type"], "main_insight")
        self.assertIn("Gross revenue totals 890.00", result["answer"])
        self.assertIn("Weighted profit margin is 24.81%", result["answer"])
        self.assertEqual(result["model"], "local")

    def test_common_quick_insight_intents_have_deterministic_routes(self):
        agent = AnalystAgent(self.dataset)
        cases = {
            "Show me revenue by region": "grouped_analysis",
            "Show monthly revenue trend": "trend",
            "What is the overall conversion rate?": "derived_metrics",
            "Show me the data quality summary": "data_quality",
            "What is the main insight?": "main_insight",
        }
        for question, expected_tool in cases.items():
            with self.subTest(question=question):
                self.assertEqual(agent.plan(question)[0].tool, expected_tool)

    def test_revenue_grouping_uses_sum_by_default_but_average_when_requested(self):
        summed = llm_analyst._try_grouped_query(
            self.dataset, "show me revenue across regions"
        )
        averaged = llm_analyst._try_grouped_query(
            self.dataset, "show average revenue across regions"
        )
        self.assertIn("SUM(", summed["sql"])
        self.assertIn("AVG(", averaged["sql"])


    def test_highest_total_revenue_ranks_groups_by_sum_not_max(self):
        result = llm_analyst._try_grouped_query(
            self.dataset,
            "Which region has the highest total revenue?",
        )
        self.assertIsNotNone(result)
        self.assertIn("SUM(", result["sql"])
        self.assertEqual(result["rows"][0]["region"], "South")
        self.assertEqual(float(result["rows"][0]["value"]), 400.0)

    def test_contextual_followup_explains_previous_grouped_result(self):
        previous = llm_analyst._try_grouped_query(
            self.dataset,
            "Show revenue by region",
        )
        history = [
            {"role": "user", "text": "Show revenue by region"},
            {
                "role": "assistant",
                "text": previous["answer"],
                "rows": previous["rows"],
                "columns": previous["columns"],
                "sql": previous["sql"],
                "visualization": previous["visualization"],
                "resultType": previous["type"],
            },
        ]
        result = llm_analyst._try_contextual_followup(
            self.dataset,
            "Explain these results",
            history,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "contextual_followup")
        self.assertIn("South", result["answer"])
        self.assertIn("400.00", result["answer"])
        self.assertIn("summed", result["answer"])
        self.assertIn("% of the displayed group total", result["answer"])

    def test_generic_category_followup_uses_previous_chart_dimension(self):
        previous = llm_analyst._try_grouped_query(
            self.dataset,
            "Show revenue by region",
        )
        history = [
            {"role": "user", "text": "Show revenue by region"},
            {
                "role": "assistant",
                "text": previous["answer"],
                "rows": previous["rows"],
                "columns": previous["columns"],
                "sql": previous["sql"],
                "visualization": previous["visualization"],
                "resultType": previous["type"],
            },
        ]
        result = llm_analyst._try_contextual_dimension_ranking(
            self.dataset,
            "Which region contributes the most?",
            history,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["rows"][0]["region"], "South")
        self.assertIn("South", result["answer"])
        self.assertIn("400.00", result["answer"])

    def test_agent_routes_chart_context_followup_without_model_fallback(self):
        previous = llm_analyst._try_grouped_query(
            self.dataset,
            "Show revenue by region",
        )
        history = [
            {"role": "user", "text": "Show revenue by region"},
            {
                "role": "assistant",
                "text": previous["answer"],
                "rows": previous["rows"],
                "columns": previous["columns"],
                "sql": previous["sql"],
                "visualization": previous["visualization"],
                "resultType": previous["type"],
            },
        ]
        result = AnalystAgent(self.dataset).run(
            "Which region contributes the most?",
            history,
        )
        self.assertEqual(result["type"], "contextual_followup")
        self.assertEqual(result["rows"][0]["region"], "South")
        self.assertEqual(result["model"], "local")

    def test_quick_insight_correlation_matrix_is_local_and_deterministic(self):
        result = llm_analyst._try_statistical_query(
            self.dataset,
            "Show the correlation matrix for numeric columns.",
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "correlation_analysis")
        self.assertGreater(len(result["rows"]), 0)
        self.assertIn("corr(", result["sql"].lower())
        self.assertIn("not causation", result["answer"].lower())


if __name__ == "__main__":
    unittest.main()
