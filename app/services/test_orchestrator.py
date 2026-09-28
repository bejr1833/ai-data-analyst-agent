from app.services.orchestrator import AnalystOrchestrator
from app.services.data_loader import load_dataset


# ============================================================
# LOAD REAL DATASET
# ============================================================

FILE_PATH = r"C:\Users\ernes\OneDrive\Desktop\sales_data.csv"

filename = "sales_data.csv"

dataset = load_dataset(
    filename,
    FILE_PATH,
)


# ============================================================
# CREATE ORCHESTRATOR
# ============================================================

agent = AnalystOrchestrator(dataset)


# ============================================================
# TEST QUESTIONS
# ============================================================

questions = [
    "What is the total revenue?",
    "Show total sales by region",
    "Which region has the highest sales?",
    "What is the correlation between revenue and marketing spend?",
]

# ============================================================
# RUN TESTS
# ============================================================

for question in questions:

    print("\n\n==============================")
    print("QUESTION:", question)
    print("==============================")

    try:

        result = agent.analyze(question)

        print("\nRESULT:")
        print(result)

    except Exception as e:

        print("\nERROR:")
        print(type(e).__name__, str(e))