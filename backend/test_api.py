import io
import os
import tempfile

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


# ============================================================
# TEST DATASET
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
"""


# ============================================================
# HELPER
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


# ============================================================
# TEST 1 — HEALTH
# ============================================================

def test_health():

    response = client.get("/health")

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "ok"


# ============================================================
# TEST 2 — API DOCUMENTATION
# ============================================================

def test_openapi():

    response = client.get("/openapi.json")

    assert response.status_code == 200

    data = response.json()

    assert "paths" in data

    assert len(data["paths"]) > 0


# ============================================================
# TEST 3 — UPLOAD DATASET
# ============================================================

def test_upload_dataset():

    file_path = create_test_csv()

    try:

        with open(
            file_path,
            "rb",
        ) as file:

            response = client.post(
                "/api/upload",
                files={
                    "file": (
                        "test_dataset.csv",
                        file,
                        "text/csv",
                    )
                },
            )

        assert response.status_code in (200, 201)

        data = response.json()

        assert isinstance(data, dict)

        assert "dataset_id" in data

        assert data["dataset_id"]

        print()
        print("Uploaded dataset ID:", data["dataset_id"])

    finally:

        if os.path.exists(file_path):

            os.remove(file_path)


# ============================================================
# TEST 4 — UPLOAD INVALID FILE
# ============================================================

def test_invalid_upload():

    response = client.post(
        "/api/upload",
        files={
            "file": (
                "test.txt",
                io.BytesIO(
                    b"This is not a CSV dataset."
                ),
                "text/plain",
            )
        },
    )

    assert response.status_code >= 400


# ============================================================
# TEST 5 — FULL DATASET FLOW
# ============================================================

def test_full_dataset_flow():

    file_path = create_test_csv()

    try:

        # ----------------------------------------------------
        # Upload
        # ----------------------------------------------------

        with open(
            file_path,
            "rb",
        ) as file:

            upload_response = client.post(
                "/api/upload",
                files={
                    "file": (
                        "test_dataset.csv",
                        file,
                        "text/csv",
                    )
                },
            )

        assert upload_response.status_code in (
            200,
            201,
        )

        upload_data = upload_response.json()

        assert "dataset_id" in upload_data

        dataset_id = upload_data["dataset_id"]

        print()
        print("=" * 60)
        print("API INTEGRATION TEST")
        print("Dataset ID:", dataset_id)
        print("=" * 60)

        # ----------------------------------------------------
        # Overview
        # ----------------------------------------------------

        overview_response = client.get(
            f"/api/datasets/{dataset_id}/overview"
        )

        assert overview_response.status_code == 200

        overview = overview_response.json()

        assert isinstance(overview, dict)

        print("[PASS] Dataset overview")

        # ----------------------------------------------------
        # Columns
        # ----------------------------------------------------

        columns_response = client.get(
            f"/api/datasets/{dataset_id}/columns"
        )

        assert columns_response.status_code == 200

        columns = columns_response.json()

        assert columns is not None

        print("[PASS] Dataset columns")

        # ----------------------------------------------------
        # Ask — Numeric
        # ----------------------------------------------------

        ask_response = client.post(
            f"/api/datasets/{dataset_id}/ask",
            json={
                "question": "What is the total revenue?"
            },
        )

        assert ask_response.status_code == 200

        result = ask_response.json()

        assert isinstance(result, dict)

        assert "answer" in result

        print("[PASS] Numeric analysis")

        # ----------------------------------------------------
        # Ask — Grouped
        # ----------------------------------------------------

        grouped_response = client.post(
            f"/api/datasets/{dataset_id}/ask",
            json={
                "question": "Show total revenue by region"
            },
        )

        assert grouped_response.status_code == 200

        grouped_result = grouped_response.json()

        assert isinstance(grouped_result, dict)

        assert "answer" in grouped_result

        print("[PASS] Grouped analysis")

        # ----------------------------------------------------
        # Ask — Business Insight
        # ----------------------------------------------------

        insight_response = client.post(
            f"/api/datasets/{dataset_id}/ask",
            json={
                "question": "Which region has the highest sales?"
            },
        )

        assert insight_response.status_code == 200

        insight_result = insight_response.json()

        assert isinstance(insight_result, dict)

        assert "answer" in insight_result

        print("[PASS] Business insight")

        # ----------------------------------------------------
        # Ask — Statistics
        # ----------------------------------------------------

        statistics_response = client.post(
            f"/api/datasets/{dataset_id}/ask",
            json={
                "question": (
                    "What is the correlation between "
                    "revenue and marketing spend?"
                )
            },
        )

        assert statistics_response.status_code == 200

        statistics_result = statistics_response.json()

        assert isinstance(statistics_result, dict)

        assert "answer" in statistics_result

        print("[PASS] Statistical analysis")

        # ----------------------------------------------------
        # Check Agent Trace
        # ----------------------------------------------------

        if "agent" in result:

            assert result["agent"] is not None

            print("[PASS] Agent trace")

        print()
        print("=" * 60)
        print("API INTEGRATION TESTS: PASSED")
        print("=" * 60)

    finally:

        if os.path.exists(file_path):

            os.remove(file_path)


# ============================================================
# RUN TESTS
# ============================================================

if __name__ == "__main__":

    print()
    print("Running AI Data Analyst API tests...")
    print()

    test_health()
    print("[PASS] Health endpoint")

    test_openapi()
    print("[PASS] OpenAPI endpoint")

    test_upload_dataset()
    print("[PASS] Dataset upload")

    test_invalid_upload()
    print("[PASS] Invalid upload handling")

    test_full_dataset_flow()