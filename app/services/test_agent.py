from app.services.agent import AnalystAgent


class FakeConnection:
    def execute(self, *_args, **_kwargs):
        class Result:
            def fetchone(self):
                return (1000,)

        return Result()


class FakeDataset:
    columns = ["date", "region", "revenue", "marketing_spend"]
    filename = "fake.csv"
    row_count = 10
    con = FakeConnection()


agent = AnalystAgent(FakeDataset())

assert agent.plan("What is the total revenue?")[0].tool == "numeric_analysis"
assert agent.plan("Show revenue trend over time")[0].tool == "trend"
assert agent.plan("Forecast revenue for next 7 days")[0].tool == "forecast"
assert agent.plan("Which region has the highest sales?")[0].tool == "business_insight"
assert (
    agent.plan(
        "What is the correlation between revenue and marketing spend?"
    )[0].tool
    == "statistics"
)
assert agent.plan("What if revenue increases by 20%?")[0].tool == "scenario"

print("Agent planner smoke test: PASSED")
