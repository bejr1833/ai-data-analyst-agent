import os
import tempfile

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


# ============================================================
# ADVANCED TEST DATASET
# ============================================================

CSV_CONTENT = """date,region,product,revenue,sales,units_sold,unit_price,marketing_spend,customer_rating,returns
2026-01-01,North,Laptop,5000,5000,10,500,1000,4.5,1
2026-01-02,South,Phone,4000,4000,20,200,800,4.2,2
2026-01-03,East,Tablet,3000,3000,15,200,600,4.0,1
2026-01-04,West,Laptop,2000,2000,5,400,400,3.8,3
2026-01-05,North,Phone,6000,6000,30,200,1200,4.7,1
2026-01-06,South,Laptop,4500,4500,9,500,900,4.3,2
2026-01-07,East,Phone,3500,3500,17,200,700,4.1,1
2026-01-08,West,Tablet,2500,2500,12,200,500,3.9,2
2026-01-09,North,Laptop,7000,7000,14,500,1400,4.8,1
2026-01-10,South,Phone,5000,5000,25,200,1000,4.4,2
2026-01-11,East,Tablet,4000,4000,20,200,800,4.2,1
2026-01-12,West,Laptop,3000,3000,6,500,600,4.0,2
2026-01-13,North,Phone,8000,8000,40,200,1600,4.9,1
2026-01-14,South,Laptop,5500,5500,11,500,1100,4.5,2
2026-01-15,East,Phone,4500,4500,22,200,900,4.3,1
2026-01-16,West,Tablet,3500,3500,17,200,700,4.1,2
2026-01-17,North,Laptop,9000,9000,18,500,1800,4.9,1
2026-01-18,South,Phone,6000,6000,30,200,1200,4.6,2
2026-01-19,East,Tablet,5000,5000,25,200,1000,4.4,1
2026-01-20,West,Laptop,4000,4000,8,500,800,4.2,2
2026-01-21,North,Phone,10000,10000,50,200,2000,5.0,1
2026-01-22,South,Laptop,6500,6500,13,500,1300,4.7,2
2026-01-23,East,Phone,5500,5500,27,200,1100,4.5,1
2026-01-24,West,Tablet,4500,4500,22,200,900,4.3,2
2026-01-25,North,Laptop,11000,11000,22,500,2200,5.0,1
2026-01-26,South,Phone,7000,7000,35,200,1400,4.8,2
2026-01-27,East,Tablet,6000,6000,30,200,1200,4.6,1
2026-01-28,West,Laptop,5000,5000,10,500,1000,4.4,2
2026-01-29,North,Phone,12000,12000,60,200,2400,5.0,1
2026-01-30,South,Laptop,7500,7500,15,500,1500,4.9,2
2026-01-31,East,Phone,6500,6500,32,200,1300,4.7,1
2026-02-01,West,Tablet,5500,5500,27,200,1100,4.5,2
2026-02-02,North,Laptop,13000,13000,26,500,2600,5.0,1
2026-02-03,South,Phone,8000,8000,40,200,1600,4.9,2
2026-02-04,East,Tablet,7000,7000,35,200,1400,4.8,1
2026-02-05,West,Laptop,6000,6000,12,500,1200,4.6,2
2026-02-06,North,Phone,14000,14000,70,200,2800,5.0,1
2026-02-07,South,Laptop,8500,8500,17,500,1700,4.9,2
2026-02-08,East,Phone,7500,7500,37,200,1500,4.8,1
2026-02-09,West,Tablet,6500,6500,32,200,1300,4.7,2
2026-02-10,North,Laptop,15000,15000,30,500,3000,5.0,1
2026-02-11,South,Phone,9000,9000,45,200,1800,4.9,2
2026-02-12,East,Tablet,8000,8000,40,200,1600,4.8,1
2026-02-13,West,Laptop,7000,7000,14,500,1400,4.7,2
2026-02-14,North,Phone,16000,16000,80,200,3200,5.0,1
2026-02-15,South,Laptop,9500,9500,19,500,1900,4.9,2
2026-02-16,East,Phone,8500,8500,42,200,1700,4.8,1
2026-02-17,West,Tablet,7500,7500,37,200,1500,4.7,2
2026-02-18,North,Laptop,17000,17000,34,500,3400,5.0,1
2026-02-19,South,Phone,10000,10000,50,200,2000,4.9,2
2026-02-20,East,Tablet,9000,9000,45,200,1800,4.8,1
2026-02-21,West,Laptop,8000,8000,16,500,1600,4.6,2
2026-02-22,North,Phone,18000,18000,90,200,3600,5.0,1
2026-02-23,South,Laptop,10500,10500,21,500,2100,4.9,2
2026-02-24,East,Phone,9500,9500,47,200,1900,4.8,1
2026-02-25,West,Tablet,8500,8500,42,200,1700,4.7,2
2026-02-26,North,Laptop,19000,19000,38,500,3800,5.0,1
2026-02-27,South,Phone,11000,11000,55,200,2200,4.9,2
2026-02-28,East,Tablet,10000,10000,50,200,2000,4.8,1
2026-03-01,West,Laptop,9000,9000,18,500,1800,4.7,2
2026-03-02,North,Phone,20000,20000,100,200,4000,5.0,1
2026-03-03,South,Laptop,11500,11500,23,500,2300,4.9,2
2026-03-04,East,Phone,10500,10500,52,200,2100,4.8,1
2026-03-05,West,Tablet,9500,9500,47,200,1900,4.7,2
2026-03-06,North,Laptop,22000,22000,44,500,4400,5.0,1
2026-03-07,South,Phone,12000,12000,60,200,2400,4.9,2
2026-03-08,East,Tablet,11000,11000,55,200,2200,4.8,1
2026-03-09,West,Laptop,10000,10000,20,500,2000,4.7,2
2026-03-10,North,Phone,23000,23000,115,200,4600,5.0,1
2026-03-11,South,Laptop,12500,12500,25,500,2500,4.9,2
2026-03-12,East,Phone,11500,11500,57,200,2300,4.8,1
2026-03-13,West,Tablet,10500,10500,52,200,2100,4.7,2
2026-03-14,North,Laptop,24000,24000,48,500,4800,5.0,1
2026-03-15,South,Phone,13000,13000,65,200,2600,4.9,2
2026-03-16,East,Tablet,12000,12000,60,200,2400,4.8,1
2026-03-17,West,Laptop,11000,11000,22,500,2200,4.7,2
2026-03-18,North,Phone,25000,25000,125,200,5000,5.0,1
2026-03-19,South,Laptop,13500,13500,27,500,2700,4.9,2
2026-03-20,East,Phone,12500,12500,62,200,2500,4.8,1
2026-03-21,West,Tablet,11500,11500,57,200,2300,4.7,2
2026-03-22,North,Laptop,26000,26000,52,500,5200,5.0,1
2026-03-23,South,Phone,14000,14000,70,200,2800,4.9,2
2026-03-24,East,Tablet,13000,13000,65,200,2600,4.8,1
2026-03-25,West,Laptop,12000,12000,24,500,2400,4.7,2
2026-03-26,North,Phone,27000,27000,135,200,5400,5.0,1
2026-03-27,South,Laptop,14500,14500,29,500,2900,4.9,2
2026-03-28,East,Phone,13500,13500,67,200,2700,4.8,1
2026-03-29,West,Tablet,12500,12500,62,200,2500,4.7,2
2026-03-30,North,Laptop,28000,28000,56,500,5600,5.0,1
2026-03-31,South,Phone,15000,15000,75,200,3000,4.9,2
2026-04-01,East,Tablet,14000,14000,70,200,2800,4.8,1
2026-04-02,West,Laptop,13000,13000,26,500,2600,4.7,2
2026-04-03,North,Laptop,100000,100000,200,500,20000,5.0,1
"""


# ============================================================
# HELPERS
# ============================================================

def create_test_csv():

    file = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".csv",
        delete=False,
        encoding="utf-8",
    )

    file.write(CSV_CONTENT)
    file.close()

    return file.name


def upload_dataset():

    file_path = create_test_csv()

    try:

        with open(file_path, "rb") as file:

            response = client.post(
                "/api/upload",
                files={
                    "file": (
                        "advanced_test.csv",
                        file,
                        "text/csv",
                    )
                },
            )

        assert response.status_code in (200, 201)

        data = response.json()

        assert "dataset_id" in data

        return data["dataset_id"]

    finally:

        if os.path.exists(file_path):
            os.remove(file_path)


def ask(dataset_id, question):

    response = client.post(
        f"/api/datasets/{dataset_id}/ask",
        json={
            "question": question
        },
    )

    assert response.status_code == 200, (
        f"Question failed: {question}\n"
        f"Status: {response.status_code}\n"
        f"Response: {response.text}"
    )

    data = response.json()

    assert isinstance(data, dict)

    assert "answer" in data

    return data


# ============================================================
# TEST 1 — TREND ANALYSIS
# ============================================================

def test_trend():

    dataset_id = upload_dataset()

    result = ask(
        dataset_id,
        "Show revenue trend over time",
    )

    assert result["answer"]

    print("[PASS] Trend analysis")


# ============================================================
# TEST 2 — FORECAST
# ============================================================

def test_forecast():

    dataset_id = upload_dataset()

    result = ask(
        dataset_id,
        "Forecast revenue for the next 7 days",
    )

    assert result["answer"]

    print("[PASS] Forecast analysis")


# ============================================================
# TEST 3 — ANOMALY DETECTION
# ============================================================

def test_anomaly_detection():

    dataset_id = upload_dataset()

    result = ask(
        dataset_id,
        "Find unusual revenue values",
    )

    assert result["answer"]

    print("[PASS] Anomaly detection")


# ============================================================
# TEST 4 — SCENARIO ANALYSIS
# ============================================================

def test_scenario():

    dataset_id = upload_dataset()

    result = ask(
        dataset_id,
        "What if revenue increases by 20%?",
    )

    assert result["answer"]

    print("[PASS] Scenario analysis")


# ============================================================
# TEST 5 — CORRELATION
# ============================================================

def test_correlation():

    dataset_id = upload_dataset()

    result = ask(
        dataset_id,
        "What is the correlation between revenue and marketing spend?",
    )

    assert result["answer"]

    print("[PASS] Correlation analysis")


# ============================================================
# TEST 6 — GROUPED VISUALIZATION
# ============================================================

def test_grouped_visualization():

    dataset_id = upload_dataset()

    result = ask(
        dataset_id,
        "Show total revenue by region",
    )

    assert result["answer"]

    if "visualization" in result:

        visualization = result["visualization"]

        assert visualization is not None

        assert isinstance(
            visualization,
            dict,
        )

    print("[PASS] Grouped visualization")


# ============================================================
# TEST 7 — AGENT TRACE
# ============================================================

def test_agent_trace():

    dataset_id = upload_dataset()

    result = ask(
        dataset_id,
        "What is the total revenue?",
    )

    assert "agent" in result

    agent = result["agent"]

    assert agent is not None

    assert "name" in agent

    assert "plan" in agent

    assert "total_duration_ms" in agent

    assert "fallback_used" in agent

    print("[PASS] Agent trace")


# ============================================================
# TEST 8 — CONVERSATION HISTORY
# ============================================================

def test_conversation_history():

    dataset_id = upload_dataset()

    first = ask(
        dataset_id,
        "What is the total revenue?",
    )

    assert first["answer"]

    response = client.post(
        f"/api/datasets/{dataset_id}/ask",
        json={
            "question": "Can you explain that?",
            "conversation_history": [
                {
                    "role": "user",
                    "content": "What is the total revenue?",
                },
                {
                    "role": "assistant",
                    "content": first["answer"],
                },
            ],
        },
    )

    assert response.status_code == 200

    result = response.json()

    assert "answer" in result

    print("[PASS] Conversation history")


# ============================================================
# TEST 9 — INVALID DATASET ID
# ============================================================

def test_invalid_dataset():

    response = client.post(
        "/api/datasets/invalid-dataset-id/ask",
        json={
            "question": "What is the total revenue?"
        },
    )

    assert response.status_code >= 400

    print("[PASS] Invalid dataset handling")


# ============================================================
# TEST 10 — EMPTY QUESTION
# ============================================================

def test_empty_question():

    dataset_id = upload_dataset()

    response = client.post(
        f"/api/datasets/{dataset_id}/ask",
        json={
            "question": ""
        },
    )

    assert response.status_code >= 400

    print("[PASS] Empty question handling")


# ============================================================
# RUN TESTS
# ============================================================

if __name__ == "__main__":

    print()
    print("Running advanced AI Data Analyst tests...")
    print()

    test_trend()

    test_forecast()

    test_anomaly_detection()

    test_scenario()

    test_correlation()

    test_grouped_visualization()

    test_agent_trace()

    test_conversation_history()

    test_invalid_dataset()

    test_empty_question()

    print()
    print("=" * 60)
    print("ADVANCED ANALYTICS TESTS: PASSED")
    print("=" * 60)