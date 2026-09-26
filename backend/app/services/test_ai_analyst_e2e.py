import os
import sys
import requests
from typing import Any


# ============================================================
# CONFIGURATION
# ============================================================

BASE_URL = "http://127.0.0.1:8000"

DATASET_ID = os.getenv("DATASET_ID")

if not DATASET_ID:
    print("ERROR: DATASET_ID environment variable is not set.")
    print()
    print(
        '$env:DATASET_ID="0dd2d7bc-a7e1-4b42-b17b-6314ff4a6d6a"'
    )
    sys.exit(1)


# ============================================================
# HELPERS
# ============================================================

def print_separator():
    print("=" * 70)


def ask(
    question: str,
    conversation_history: list[dict[str, Any]] | None = None,
):
    """
    Send a question to the AI Data Analyst backend.
    """

    url = f"{BASE_URL}/api/datasets/{DATASET_ID}/ask"

    payload = {
        "question": question
    }

    if conversation_history is not None:
        payload["conversation_history"] = conversation_history

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=120,
        )
    except requests.RequestException as exc:
        print(f"REQUEST ERROR: {exc}")

        return {
            "_http_status": None,
            "error": str(exc),
        }

    print(f"HTTP: {response.status_code}")

    try:
        result = response.json()
    except ValueError:
        print("ERROR: Backend returned invalid JSON.")
        print(response.text[:1000])

        return {
            "_http_status": response.status_code,
            "error": "Invalid JSON response",
        }

    result["_http_status"] = response.status_code

    return result


def get_plan_tools(result: dict[str, Any]) -> list[str]:
    """
    Extract tool names from the AI agent execution plan.
    """

    agent = result.get("agent")

    if not isinstance(agent, dict):
        return []

    plan = agent.get("plan", [])

    if not isinstance(plan, list):
        return []

    tools = []

    for step in plan:
        if isinstance(step, dict):
            tool = step.get("tool")

            if tool:
                tools.append(str(tool))

    return tools


def print_result(
    question: str,
    result: dict[str, Any],
):
    """
    Print a complete AI Analyst result.
    """

    print()
    print(f"QUESTION: {question}")

    answer = result.get("answer")

    print("ANSWER:")

    if answer:
        print(answer)
    else:
        print("(No answer returned)")

    print()

    print(
        f"RESULT TYPE: "
        f"{result.get('type')}"
    )

    rows = result.get("rows", [])

    if isinstance(rows, list):
        print(
            f"ROWS: {len(rows)}"
        )
    else:
        print("ROWS: 0")

    visualization = result.get(
        "visualization"
    )

    if isinstance(visualization, dict):
        print(
            "VISUALIZATION TYPE: "
            f"{visualization.get('type')}"
        )

        print(
            "VISUALIZATION TITLE: "
            f"{visualization.get('title')}"
        )

    agent = result.get("agent")

    if isinstance(agent, dict):

        print(
            "AGENT: "
            f"{agent.get('name')}"
        )

        plan = agent.get("plan", [])

        if isinstance(plan, list):
            print("PLAN:")

            for step in plan:

                if isinstance(step, dict):

                    print(
                        f"  - "
                        f"{step.get('tool')}: "
                        f"{step.get('reason', '')}"
                    )


def check_http(
    result: dict[str, Any],
    name: str,
) -> bool:

    if result.get("_http_status") != 200:

        print(
            f"FAIL - {name}: "
            f"HTTP {result.get('_http_status')}"
        )

        return False

    return True


def check_answer(
    result: dict[str, Any],
    name: str,
) -> bool:

    answer = result.get("answer")

    if not isinstance(answer, str):
        print(
            f"FAIL - {name}: "
            "answer missing"
        )

        return False

    if not answer.strip():
        print(
            f"FAIL - {name}: "
            "empty answer"
        )

        return False

    return True


# ============================================================
# HEADER
# ============================================================

print_separator()
print("AI DATA ANALYST AGENT - E2E TEST")
print_separator()

print(
    f"Dataset ID: {DATASET_ID}"
)

print(
    f"Backend: {BASE_URL}"
)

print()


# ============================================================
# 1. BACKEND HEALTH
# ============================================================

print_separator()
print("1. BACKEND HEALTH")
print_separator()

try:

    health_response = requests.get(
        f"{BASE_URL}/health",
        timeout=10,
    )

    print(
        f"Status: "
        f"{health_response.status_code}"
    )

    print(
        f"Response: "
        f"{health_response.text}"
    )

    health_ok = (
        health_response.status_code == 200
    )

    print(
        "PASS"
        if health_ok
        else "FAIL"
    )

except requests.RequestException as exc:

    print(
        f"FAIL: {exc}"
    )

    sys.exit(1)


# ============================================================
# 2. TOTAL REVENUE
# ============================================================

question = "What is the total revenue?"

result_total = ask(question)

print_result(
    question,
    result_total,
)

total_ok = (
    check_http(
        result_total,
        "Total revenue",
    )
    and check_answer(
        result_total,
        "Total revenue",
    )
)

print(
    "PASS - Total revenue"
    if total_ok
    else "FAIL - Total revenue"
)


# ============================================================
# 3. REVENUE BY REGION
# ============================================================

question = "Show total revenue by region"

result_region = ask(question)

print_result(
    question,
    result_region,
)

region_rows = result_region.get(
    "rows",
    [],
)

region_ok = (
    check_http(
        result_region,
        "Revenue by region",
    )
    and check_answer(
        result_region,
        "Revenue by region",
    )
    and isinstance(
        region_rows,
        list,
    )
    and len(region_rows) >= 2
)

print(
    "PASS - Revenue by region"
    if region_ok
    else "FAIL - Revenue by region"
)


# ============================================================
# 4. HIGHEST REVENUE REGION
# ============================================================

question = (
    "Which region has the highest revenue?"
)

result_highest = ask(question)

print_result(
    question,
    result_highest,
)

highest_ok = (
    check_http(
        result_highest,
        "Highest revenue region",
    )
    and check_answer(
        result_highest,
        "Highest revenue region",
    )
)

print(
    "PASS - Highest revenue region"
    if highest_ok
    else "FAIL - Highest revenue region"
)


# ============================================================
# 5. TOP N PRODUCTS
# ============================================================

question = (
    "Show the top 5 products by revenue"
)

result_top = ask(question)

print_result(
    question,
    result_top,
)

top_rows = result_top.get(
    "rows",
    [],
)

top_tools = get_plan_tools(
    result_top
)

print()
print(
    f"Top-N rows returned: "
    f"{len(top_rows)}"
)

print(
    f"Top-N agent tools: "
    f"{top_tools}"
)

# Dataset has 3 products.
# Therefore top 5 should return all 3.
top_ok = (
    check_http(
        result_top,
        "Top N products",
    )
    and check_answer(
        result_top,
        "Top N products",
    )
    and isinstance(
        top_rows,
        list,
    )
    and len(top_rows) >= 2
)

print(
    "PASS - Top N products"
    if top_ok
    else "FAIL - Top N products"
)


# ============================================================
# 6. REVENUE TREND
# ============================================================

question = (
    "Show revenue trend over time"
)

result_trend = ask(question)

print_result(
    question,
    result_trend,
)

trend_rows = result_trend.get(
    "rows",
    [],
)

trend_ok = (
    check_http(
        result_trend,
        "Revenue trend",
    )
    and check_answer(
        result_trend,
        "Revenue trend",
    )
    and isinstance(
        trend_rows,
        list,
    )
    and len(trend_rows) >= 2
)

print(
    "PASS - Revenue trend"
    if trend_ok
    else "FAIL - Revenue trend"
)


# ============================================================
# 7. CORRELATION
# ============================================================

question = (
    "What is the correlation between "
    "revenue and marketing spend?"
)

result_correlation = ask(question)

print_result(
    question,
    result_correlation,
)

correlation_ok = (
    check_http(
        result_correlation,
        "Correlation",
    )
    and check_answer(
        result_correlation,
        "Correlation",
    )
)

print(
    "PASS - Correlation"
    if correlation_ok
    else "FAIL - Correlation"
)


# ============================================================
# 8. FORECAST
# ============================================================

question = (
    "Forecast revenue for the next 7 days"
)

result_forecast = ask(question)

print_result(
    question,
    result_forecast,
)

forecast_rows = result_forecast.get(
    "rows",
    [],
)

forecast_ok = (
    check_http(
        result_forecast,
        "Forecast",
    )
    and check_answer(
        result_forecast,
        "Forecast",
    )
    and isinstance(
        forecast_rows,
        list,
    )
    and len(forecast_rows) >= 7
)

print(
    "PASS - Forecast"
    if forecast_ok
    else "FAIL - Forecast"
)


# ============================================================
# 9. WHAT-IF ANALYSIS
# ============================================================

question = (
    "What if revenue increases by 20%?"
)

result_what_if = ask(question)

print_result(
    question,
    result_what_if,
)

what_if_ok = (
    check_http(
        result_what_if,
        "What-if analysis",
    )
    and check_answer(
        result_what_if,
        "What-if analysis",
    )
)

print(
    "PASS - What-if analysis"
    if what_if_ok
    else "FAIL - What-if analysis"
)


# ============================================================
# 10. DATA QUALITY
# ============================================================

question = (
    "Show me the data quality summary"
)

result_quality = ask(question)

print_result(
    question,
    result_quality,
)

quality_rows = result_quality.get(
    "rows",
    [],
)

quality_ok = (
    check_http(
        result_quality,
        "Data quality",
    )
    and check_answer(
        result_quality,
        "Data quality",
    )
    and isinstance(
        quality_rows,
        list,
    )
    and len(quality_rows) >= 1
)

print(
    "PASS - Data quality"
    if quality_ok
    else "FAIL - Data quality"
)


# ============================================================
# 11. CONVERSATION FOLLOW-UP
# ============================================================

print()
print_separator()
print("11. CONVERSATION FOLLOW-UP")
print_separator()


# ------------------------------------------------------------
# FIRST QUESTION
# ------------------------------------------------------------

first_question = (
    "What is the total revenue?"
)

first_result = ask(
    first_question
)

first_answer = first_result.get(
    "answer",
    "",
)


# ------------------------------------------------------------
# BUILD COMPLETE CONVERSATION HISTORY
# ------------------------------------------------------------

conversation_history = [
    {
        "role": "user",
        "text": first_question,
    },
    {
        "role": "assistant",
        "text": first_answer,
        "rows": first_result.get("rows", []),
        "visualization": first_result.get("visualization"),
        "sql": first_result.get("sql"),
    },
]


# ============================================================
# DEBUG HISTORY
# ============================================================

print()
print("CONVERSATION HISTORY DEBUG")
print("-" * 70)

for index, message in enumerate(
    conversation_history,
    start=1,
):

    print(
        f"MESSAGE {index}"
    )

    print(
        f"ROLE: "
        f"{message.get('role')}"
    )

    print(
        f"TEXT: "
        f"{message.get('text')}"
    )

    print(
        f"CONTENT: "
        f"{message.get('content')}"
    )

    rows = message.get(
        "rows",
        [],
    )

    print(
        f"ROWS: "
        f"{len(rows) if isinstance(rows, list) else 0}"
    )

    print(
        f"RESULT TYPE: "
        f"{message.get('resultType')}"
    )

    print(
        f"SQL: "
        f"{message.get('sql')}"
    )

    print()


# ============================================================
# FOLLOW-UP QUESTION
# ============================================================

follow_up_question = (
    "Can you explain that?"
)

follow_up_result = ask(
    follow_up_question,
    conversation_history=conversation_history,
)

print_result(
    follow_up_question,
    follow_up_result,
)


# ============================================================
# STRICT FOLLOW-UP VALIDATION
# ============================================================

follow_up_tools = get_plan_tools(
    follow_up_result
)

follow_up_answer = follow_up_result.get(
    "answer",
    "",
)

print()
print(
    f"Follow-up agent tools: "
    f"{follow_up_tools}"
)


follow_up_type = str(
    follow_up_result.get("type", "")
).lower()

follow_up_model = str(
    follow_up_result.get("model", "")
).lower()

print(
    f"Follow-up result type: "
    f"{follow_up_result.get('type')}"
)

print(
    f"Follow-up model: "
    f"{follow_up_result.get('model')}"
)

print(
    f"Follow-up agent tools: "
    f"{follow_up_tools}"
)

follow_up_ok = (
    check_http(
        follow_up_result,
        "Conversation follow-up",
    )
    and isinstance(
        follow_up_answer,
        str,
    )
    and bool(
        follow_up_answer.strip()
    )
    and follow_up_type == "contextual_followup"
    and "contextual_followup" in follow_up_tools
    and follow_up_model == "local"
)


if follow_up_ok:

    print(
        "PASS - Conversation follow-up"
    )

else:

    print(
        "FAIL - Conversation follow-up"
    )

    print()

    print(
        "EXPECTED TOOL:"
    )

    print(
        "  contextual_followup"
    )

    print()

    print(
        "ACTUAL TOOLS:"
    )

    if follow_up_tools:

        for tool in follow_up_tools:

            print(
                f"  {tool}"
            )

    else:

        print(
            "  No agent tool returned"
        )


# ============================================================
# FINAL SUMMARY
# ============================================================

print()
print_separator()
print("E2E TEST COMPLETE")
print_separator()

tests = [
    (
        "Backend health",
        health_ok,
    ),

    (
        "Total revenue",
        total_ok,
    ),

    (
        "Revenue by region",
        region_ok,
    ),

    (
        "Highest revenue region",
        highest_ok,
    ),

    (
        "Top N products",
        top_ok,
    ),

    (
        "Revenue trend",
        trend_ok,
    ),

    (
        "Correlation",
        correlation_ok,
    ),

    (
        "Forecast",
        forecast_ok,
    ),

    (
        "What-if analysis",
        what_if_ok,
    ),

    (
        "Data quality",
        quality_ok,
    ),

    (
        "Conversation follow-up",
        follow_up_ok,
    ),
]


failed_tests = []


for name, passed in tests:

    if passed:

        print(
            f"PASS - {name}"
        )

    else:

        print(
            f"FAIL - {name}"
        )

        failed_tests.append(name)


print()


# ============================================================
# FINAL RESULT
# ============================================================

if failed_tests:

    print_separator()
    print("FAILED TESTS")
    print_separator()

    for test in failed_tests:

        print(
            f"  - {test}"
        )

    print()

    print(
        f"{len(failed_tests)} "
        f"test(s) failed."
    )

    print()

    sys.exit(1)


else:

    print_separator()
    print("ALL E2E TESTS PASSED")
    print_separator()

    print()

    print(
        "The AI Data Analyst Agent passed "
        "all configured end-to-end checks."
    )

    sys.exit(0)
    