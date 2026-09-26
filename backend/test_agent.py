from app.services.agent import AnalystAgent


# ============================================================
# FAKE DATABASE RESULT
# ============================================================

class FakeResult:

    def __init__(self, value=1000, rows=None, columns=None):
        self.value = value
        self.rows = rows or []
        self._columns = columns or ["value"]

    def fetchone(self):
        return (self.value,)

    def fetchall(self):
        return self.rows

    @property
    def description(self):
        return [(column,) for column in self._columns]


# ============================================================
# FAKE DUCKDB CONNECTION
# ============================================================

class FakeConnection:

    def execute(self, query, *_args, **_kwargs):

        query_lower = query.lower()

        if "group by" in query_lower:

            return FakeResult(
                rows=[
                    ("North", 5000),
                    ("South", 4000),
                    ("East", 3000),
                    ("West", 2000),
                ],
                columns=[
                    "region",
                    "total_revenue",
                ],
            )

        if "corr" in query_lower:

            return FakeResult(
                value=0.82,
                columns=["correlation"],
            )

        return FakeResult(
            value=1000,
            columns=["value"],
        )


# ============================================================
# FAKE DATASET
# ============================================================

class FakeDataset:

    columns = [
        "date",
        "region",
        "product",
        "revenue",
        "sales",
        "units_sold",
        "unit_price",
        "marketing_spend",
        "customer_rating",
        "returns",
    ]

    filename = "fake.csv"

    row_count = 100

    con = FakeConnection()


# ============================================================
# TEST 1 — AGENT PLANNING
# ============================================================

def test_agent_planning():

    agent = AnalystAgent(FakeDataset())

    tests = [
        (
            "What is the total revenue?",
            "numeric_analysis",
        ),
        (
            "Show total revenue by region",
            "grouped_analysis",
        ),
        (
            "Which region has the highest sales?",
            "business_insight",
        ),
        (
            "Show revenue trend over time",
            "trend",
        ),
        (
            "Forecast revenue for the next 7 days",
            "forecast",
        ),
        (
            "What is the correlation between revenue and marketing spend?",
            "statistics",
        ),
        (
            "Find unusual revenue values",
            "anomaly_detection",
        ),
        (
            "What if revenue increases by 20%?",
            "scenario",
        ),
    ]

    for question, expected_tool in tests:

        steps = agent.plan(question)

        assert steps, (
            f"No plan generated for: {question}"
        )

        actual_tool = steps[0].tool

        assert actual_tool == expected_tool, (
            f"\nQuestion: {question}"
            f"\nExpected: {expected_tool}"
            f"\nActual: {actual_tool}"
        )


# ============================================================
# TEST 2 — EMPTY QUESTION
# ============================================================

def test_agent_empty_question():

    agent = AnalystAgent(FakeDataset())

    try:

        agent.run("")

    except ValueError as exc:

        assert "empty" in str(exc).lower()

    else:

        raise AssertionError(
            "Empty question should raise ValueError."
        )


# ============================================================
# TEST 3 — DATASET SCHEMA
# ============================================================

def test_dataset_schema():

    dataset = FakeDataset()

    assert "revenue" in dataset.columns
    assert "sales" in dataset.columns
    assert "region" in dataset.columns
    assert "marketing_spend" in dataset.columns
    assert "units_sold" in dataset.columns
    assert "customer_rating" in dataset.columns
    assert "returns" in dataset.columns


# ============================================================
# TEST 4 — DATASET METADATA
# ============================================================

def test_dataset_metadata():

    dataset = FakeDataset()

    assert dataset.filename == "fake.csv"
    assert dataset.row_count == 100
    assert dataset.con is not None


# ============================================================
# TEST 5 — FAKE DATABASE
# ============================================================

def test_fake_database_numeric():

    dataset = FakeDataset()

    result = dataset.con.execute(
        "SELECT SUM(revenue) FROM data"
    )

    assert result.fetchone()[0] == 1000


# ============================================================
# TEST 6 — FAKE DATABASE GROUPING
# ============================================================

def test_fake_database_grouping():

    dataset = FakeDataset()

    result = dataset.con.execute(
        """
        SELECT region, SUM(revenue)
        FROM data
        GROUP BY region
        """
    )

    rows = result.fetchall()

    assert len(rows) == 4

    assert rows[0][0] == "North"
    assert rows[0][1] == 5000


# ============================================================
# TEST 7 — FAKE DATABASE CORRELATION
# ============================================================

def test_fake_database_correlation():

    dataset = FakeDataset()

    result = dataset.con.execute(
        """
        SELECT CORR(revenue, marketing_spend)
        FROM data
        """
    )

    correlation = result.fetchone()[0]

    assert correlation == 0.82


# ============================================================
# TEST 8 — PLAN STRUCTURE
# ============================================================

def test_plan_structure():

    dataset = FakeDataset()

    agent = AnalystAgent(dataset)

    steps = agent.plan(
        "What is the total revenue?"
    )

    assert steps

    step = steps[0]

    assert hasattr(step, "tool")


# ============================================================
# TEST 9 — INVALID QUESTION TYPE
# ============================================================

def test_invalid_question_type():

    dataset = FakeDataset()

    agent = AnalystAgent(dataset)

    try:

        agent.run(None)

    except (ValueError, TypeError):

        pass

    else:

        raise AssertionError(
            "Invalid question should raise ValueError or TypeError."
        )


# ============================================================
# TEST 10 — ALL PLANNING INTENTS
# ============================================================

def test_all_planning_intents():

    dataset = FakeDataset()

    agent = AnalystAgent(dataset)

    questions = [
        "total revenue",
        "revenue by region",
        "highest sales region",
        "revenue trend",
        "forecast revenue",
        "correlation between revenue and marketing spend",
        "unusual revenue values",
        "what if revenue increases by 20 percent",
    ]

    for question in questions:

        steps = agent.plan(question)

        assert steps, (
            f"No plan generated for: {question}"
        )


# ============================================================
# RUN TESTS
# ============================================================

if __name__ == "__main__":

    print()
    print("Running AI Data Analyst Agent tests...")
    print()

    test_agent_planning()
    print("[PASS] Agent planning")

    test_agent_empty_question()
    print("[PASS] Empty question validation")

    test_dataset_schema()
    print("[PASS] Dataset schema")

    test_dataset_metadata()
    print("[PASS] Dataset metadata")

    test_fake_database_numeric()
    print("[PASS] Numeric database operation")

    test_fake_database_grouping()
    print("[PASS] Grouped database operation")

    test_fake_database_correlation()
    print("[PASS] Correlation database operation")

    test_plan_structure()
    print("[PASS] Plan structure")

    test_invalid_question_type()
    print("[PASS] Invalid question handling")

    test_all_planning_intents()
    print("[PASS] Planning intent coverage")

    print()
    print("=" * 60)
    print("AI DATA ANALYST AGENT TESTS: PASSED")
    print("=" * 60)