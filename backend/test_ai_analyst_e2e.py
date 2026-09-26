import os
import requests


# ============================================================
# CONFIGURATION
# ============================================================

BASE_URL = "http://127.0.0.1:8000"

DATASET_ID = os.getenv(
    "DATASET_ID",
    "e26d1fa0-66b1-4650-b4f3-49715c9992a7",
)

TIMEOUT = 120


# ============================================================
# HELPERS
# ============================================================

def separator():
    print("=" * 70)


def check_http(result, name):
    status = result.get("_status_code")

    print(f"HTTP: {status}")

    if status == 200:
        return True

    print(
        f"FAIL - {name}: "
        f"{result.get('_error', result)}"
    )

    return False


def check_answer(result, name):
    answer = result.get("answer", "")

    if isinstance(answer, str) and answer.strip():
        return True

    print(f"FAIL - {name}: empty answer")
    return False


def get_plan_tools(result):
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
                tools.append(tool)

    return tools


def ask(question, conversation_history=None):
    payload = {
        "question": question,
    }

    if conversation_history is not None:
        payload["conversation_history"] = conversation_history

    url = (
        f"{BASE_URL}/api/datasets/"
        f"{DATASET_ID}/ask"
    )

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=TIMEOUT,
        )

        try:
            result = response.json()
        except Exception:
            result = {
                "answer": response.text,
            }

        if not isinstance(result, dict):
            result = {
                "answer": str(result),
            }

        result["_status_code"] = response.status_code

        return result

    except Exception as exc:
        return {
            "_status_code": None,
            "_error": repr(exc),
            "answer": "",
        }


def print_result(question, result):
    print()
    print(f"HTTP: {result.get('_status_code')}")
    print()
    print(f"QUESTION: {question}")

    print("ANSWER:")

    answer = result.get(
        "answer",
        "",
    )

    print(answer)

    print()

    print(
        f"RESULT TYPE: "
        f"{result.get('type')}"
    )

    rows = result.get(
        "rows",
        [],
    )

    print(
        f"ROWS: "
        f"{len(rows) if isinstance(rows, list) else 0}"
    )

    visualization = result.get(
        "visualization"
    )

    if isinstance(
        visualization,
        dict,
    ):
        print(
            f"VISUALIZATION TYPE: "
            f"{visualization.get('type')}"
        )

        print(
            f"VISUALIZATION TITLE: "
            f"{visualization.get('title')}"
        )

    agent = result.get(
        "agent"
    )

    if isinstance(
        agent,
        dict,
    ):
        print(
            f"AGENT: "
            f"{agent.get('name')}"
        )

        plan = agent.get(
            "plan",
            [],
        )

        if isinstance(
            plan,
            list,
        ):
            print("PLAN:")

            for step in plan:
                if isinstance(
                    step,
                    dict,
                ):
                    print(
                        f"  - "
                        f"{step.get('tool')}: "
                        f"{step.get('reason', '')}"
                    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    separator()
    print("AI DATA ANALYST AGENT - E2E TEST")
    separator()

    print(
        f"Dataset ID: "
        f"{DATASET_ID}"
    )

    print(
        f"Backend: "
        f"{BASE_URL}"
    )

    print()

    # ========================================================
    # 1. HEALTH
    # ========================================================

    separator()
    print("1. BACKEND HEALTH")
    separator()

    try:
        response = requests.get(
            f"{BASE_URL}/health",
            timeout=20,
        )

        print(
            f"Status: "
            f"{response.status_code}"
        )

        print(
            f"Response: "
            f"{response.text}"
        )

        health_ok = (
            response.status_code == 200
        )

    except Exception as exc:

        print(
            f"Health check failed: "
            f"{exc}"
        )

        health_ok = False


    # ========================================================
    # 2. TOTAL REVENUE
    # ========================================================

    separator()
    print("2. TOTAL REVENUE")
    separator()

    question = (
        "What is the total revenue?"
    )

    result_total = ask(
        question
    )

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

    visualization = result_total.get(
        "visualization"
    )

    if isinstance(
        visualization,
        dict,
    ):

        if visualization.get(
            "type"
        ) != "metric":

            print(
                "WARNING: Expected "
                f"visualization 'metric', "
                f"got "
                f"'{visualization.get('type')}'"
            )


    # ========================================================
    # 3. REVENUE BY REGION
    # ========================================================

    separator()
    print("3. REVENUE BY REGION")
    separator()

    question = (
        "Show total revenue by region"
    )

    result_region = ask(
        question
    )

    print_result(
        question,
        result_region,
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
    )


    # ========================================================
    # 4. HIGHEST REVENUE REGION
    # ========================================================

    separator()
    print("4. HIGHEST REVENUE REGION")
    separator()

    question = (
        "Which region has the highest revenue?"
    )

    result_highest = ask(
        question
    )

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


    # ========================================================
    # 5. TOP PRODUCTS
    # ========================================================

    separator()
    print("5. TOP N PRODUCTS")
    separator()

    question = (
        "Show the top 5 products by revenue"
    )

    result_top = ask(
        question
    )

    print_result(
        question,
        result_top,
    )

    top_rows = result_top.get(
        "rows",
        [],
    )

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
        and len(top_rows) >= 1
    )


    # ========================================================
    # 6. REVENUE TREND
    # ========================================================

    separator()
    print("6. REVENUE TREND")
    separator()

    question = (
        "Show revenue trend over time"
    )

    result_trend = ask(
        question
    )

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
        and len(trend_rows) >= 1
    )


    # ========================================================
    # 7. CORRELATION
    # ========================================================

    separator()
    print("7. CORRELATION")
    separator()

    question = (
        "What is the correlation between "
        "revenue and marketing spend?"
    )

    result_correlation = ask(
        question
    )

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


    # ========================================================
    # 8. FORECAST
    # ========================================================

    separator()
    print("8. FORECAST")
    separator()

    question = (
        "Forecast revenue for the next 7 days"
    )

    result_forecast = ask(
        question
    )

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


    # ========================================================
    # 9. WHAT-IF
    # ========================================================

    separator()
    print("9. WHAT-IF ANALYSIS")
    separator()

    question = (
        "What if revenue increases by 20%?"
    )

    result_what_if = ask(
        question
    )

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


    # ========================================================
    # 10. DATA QUALITY
    # ========================================================

    separator()
    print("10. DATA QUALITY")
    separator()

    question = (
        "Show me the data quality summary"
    )

    result_quality = ask(
        question
    )

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


    # ========================================================
    # 11. CONVERSATION FOLLOW-UP
    # ========================================================

    print()
    separator()
    print("11. CONVERSATION FOLLOW-UP")
    separator()

    # --------------------------------------------------------
    # FIRST QUESTION
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # MINIMAL CONVERSATION HISTORY
    #
    # IMPORTANT:
    # Do NOT send model, agent, or resultType here.
    # --------------------------------------------------------

    conversation_history = [
        {
            "role": "user",
            "text": first_question,
        },
        {
            "role": "assistant",
            "text": first_answer,
            "rows": first_result.get(
                "rows",
                [],
            ),
            "visualization": first_result.get(
                "visualization"
            ),
            "sql": first_result.get(
                "sql"
            ),
        },
    ]

    # --------------------------------------------------------
    # DEBUG HISTORY
    # --------------------------------------------------------

    print()
    print(
        "CONVERSATION HISTORY DEBUG"
    )
    print(
        "-" * 70
    )

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

        rows = message.get(
            "rows",
            [],
        )

        print(
            f"ROWS: "
            f"{len(rows) if isinstance(rows, list) else 0}"
        )

        print(
            f"SQL: "
            f"{message.get('sql')}"
        )

        print()

    # --------------------------------------------------------
    # FOLLOW-UP QUESTION
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # STRICT FOLLOW-UP VALIDATION
    # --------------------------------------------------------

    follow_up_tools = get_plan_tools(
        follow_up_result
    )

    follow_up_answer = follow_up_result.get(
        "answer",
        "",
    )

    follow_up_type = str(
        follow_up_result.get(
            "type",
            "",
        )
    ).lower()

    follow_up_model = str(
        follow_up_result.get(
            "model",
            "",
        )
    ).lower()

    print()

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
        and follow_up_type
        == "contextual_followup"
        and "contextual_followup"
        in follow_up_tools
        and follow_up_model
        == "local"
    )

    if follow_up_ok:

        print()
        print(
            "PASS - Conversation follow-up"
        )

    else:

        print()
        print(
            "FAIL - Conversation follow-up"
        )

        print()
        print(
            "EXPECTED:"
        )

        print(
            "  Type: "
            "contextual_followup"
        )

        print(
            "  Model: local"
        )

        print(
            "  Tool: "
            "contextual_followup"
        )

    # ========================================================
    # FINAL SUMMARY
    # ========================================================

    print()
    separator()
    print("E2E TEST COMPLETE")
    separator()

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

            failed_tests.append(
                name
            )

    print()

    separator()

    if not failed_tests:

        print(
            "ALL E2E TESTS PASSED"
        )

    else:

        print(
            "E2E TESTS FAILED"
        )

        print()
        print(
            "Failed tests:"
        )

        for name in failed_tests:

            print(
                f"  - {name}"
            )

    separator()


if __name__ == "__main__":
    main()