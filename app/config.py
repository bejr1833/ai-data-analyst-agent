import os

# Where uploaded datasets and duckdb catalog files live
STORAGE_DIR = os.environ.get("STORAGE_DIR", os.path.join(os.path.dirname(__file__), "..", "storage"))
os.makedirs(STORAGE_DIR, exist_ok=True)

# Above this row count, we only run heavy per-row visual operations
# (scatter samples, etc.) on a random SAMPLE rather than the full table.
# Aggregate metrics (count, mean, stddev, missing %, correlations) are
# always computed on the FULL dataset via DuckDB, which streams from
# disk rather than loading everything into memory.
LARGE_DATASET_ROW_THRESHOLD = int(os.environ.get("LARGE_DATASET_ROW_THRESHOLD", 200_000))
SAMPLE_SIZE_FOR_PLOTS = int(os.environ.get("SAMPLE_SIZE_FOR_PLOTS", 20_000))

# Max distinct values before a text column is treated as "high cardinality"
# and excluded from bar-chart-of-categories rendering (e.g. free-text/IDs).
CATEGORICAL_MAX_CARDINALITY = int(os.environ.get("CATEGORICAL_MAX_CARDINALITY", 50))

MAX_UPLOAD_SIZE_BYTES = int(os.environ.get("MAX_UPLOAD_SIZE_BYTES", 2 * 1024 * 1024 * 1024))  # 2GB
