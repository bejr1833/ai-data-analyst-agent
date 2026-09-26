"""
Dataset profiling utilities.

All statistics are calculated using DuckDB against the
dataset's main_table.

The Dataset object contains:
    - dataset_id
    - filename
    - con
    - columns
    - row_count

Column data types are retrieved from DuckDB's
information_schema.columns.
"""

import math

from app.config import (
    CATEGORICAL_MAX_CARDINALITY,
)

from app.services.data_loader import (
    Dataset,
    numeric_columns,
    categorical_columns,
    datetime_columns,
)


# ============================================================
# SQL IDENTIFIER QUOTING
# ============================================================

def _q(column: str) -> str:
    """
    Safely quote a DuckDB column name.
    """
    return '"' + column.replace('"', '""') + '"'


# ============================================================
# COLUMN TYPES
# ============================================================

def _column_types(dataset: Dataset) -> dict[str, str]:
    """
    Return DuckDB data types for every column.

    Example:
        {
            "Sales": "DOUBLE",
            "Region": "VARCHAR"
        }
    """

    rows = dataset.con.execute(
        """
        SELECT
            column_name,
            data_type
        FROM information_schema.columns
        WHERE table_name = 'main_table'
        ORDER BY ordinal_position
        """
    ).fetchall()

    return {
        str(column): str(dtype)
        for column, dtype in rows
    }


# ============================================================
# OVERVIEW
# ============================================================

def overview_metrics(dataset: Dataset) -> dict:
    """
    Calculate high-level dataset statistics.
    """

    con = dataset.con.cursor()

    # --------------------------------------------------------
    # Duplicate rows
    # --------------------------------------------------------

    if dataset.row_count > 0:

        result = con.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT DISTINCT *
                FROM main_table
            ) AS distinct_rows
            """
        ).fetchone()

        if result is None or result[0] is None:
            distinct_rows = dataset.row_count
        else:
            distinct_rows = int(result[0])

        duplicate_count = max(
            0,
            dataset.row_count - distinct_rows,
        )

    else:
        duplicate_count = 0

    # --------------------------------------------------------
    # Missing values
    # --------------------------------------------------------

    total_cells = (
        dataset.row_count *
        len(dataset.columns)
    )

    if dataset.columns and dataset.row_count > 0:

        missing_exprs = ", ".join(
            f"""
            SUM(
                CASE
                    WHEN {_q(column)} IS NULL
                    THEN 1
                    ELSE 0
                END
            )
            """
            for column in dataset.columns
        )

        result = con.execute(
            f"""
            SELECT {missing_exprs}
            FROM main_table
            """
        ).fetchone()

        if result is None:
            total_missing = 0
        else:
            total_missing = sum(
                int(value or 0)
                for value in result
            )

    else:
        total_missing = 0

    # --------------------------------------------------------
    # Return
    # --------------------------------------------------------

    return {
        "dataset_id": dataset.dataset_id,
        "filename": dataset.filename,

        "row_count": int(
            dataset.row_count
        ),

        "column_count": len(
            dataset.columns
        ),

        "duplicate_rows": int(
            duplicate_count
        ),

        "total_missing_cells": int(
            total_missing
        ),

        "missing_cell_pct": (
            round(
                100 * total_missing / total_cells,
                3,
            )
            if total_cells
            else 0.0
        ),

        "numeric_column_count": len(
            numeric_columns(dataset)
        ),

        "categorical_column_count": len(
            categorical_columns(dataset)
        ),

        "datetime_column_count": len(
            datetime_columns(dataset)
        ),
    }


# ============================================================
# COLUMN PROFILES
# ============================================================

def column_profiles(
    dataset: Dataset,
) -> list[dict]:
    """
    Generate statistics for every column.

    This version does NOT use:
        dataset.dtypes

    Instead, types are retrieved directly from DuckDB.
    """

    con = dataset.con.cursor()

    types = _column_types(dataset)

    num_cols = set(
        numeric_columns(dataset)
    )

    profiles = []

    for column in dataset.columns:

        q = _q(column)

        # ----------------------------------------------------
        # Missing + distinct values
        # ----------------------------------------------------

        result = con.execute(
            f"""
            SELECT
                SUM(
                    CASE
                        WHEN {q} IS NULL
                        THEN 1
                        ELSE 0
                    END
                ),
                COUNT(
                    DISTINCT {q}
                )
            FROM main_table
            """
        ).fetchone()

        if result is None:
            n_missing = 0
            n_distinct = 0
        else:
            n_missing, n_distinct = result

        n_missing = int(
            n_missing or 0
        )

        n_distinct = int(
            n_distinct or 0
        )

        # ----------------------------------------------------
        # Basic information
        # ----------------------------------------------------

        entry = {
            "column": column,

            # FIX:
            # Use DuckDB metadata instead of dataset.dtypes
            "dtype": types.get(
                column,
                "unknown",
            ),

            "missing_count": n_missing,

            "missing_pct": (
                round(
                    100 *
                    n_missing /
                    dataset.row_count,
                    3,
                )
                if dataset.row_count
                else 0.0
            ),

            "distinct_count": n_distinct,
        }

        # ----------------------------------------------------
        # Numeric statistics
        # ----------------------------------------------------

        if column in num_cols:

            stats = con.execute(
                f"""
                SELECT
                    MIN({q}),
                    MAX({q}),
                    AVG({q}),
                    MEDIAN({q}),
                    STDDEV_SAMP({q}),
                    QUANTILE_CONT(
                        {q},
                        0.25
                    ),
                    QUANTILE_CONT(
                        {q},
                        0.75
                    )
                FROM main_table
                WHERE {q} IS NOT NULL
                """
            ).fetchone()

            if stats is None:

                (
                    minimum,
                    maximum,
                    average,
                    median,
                    std,
                    q25,
                    q75,
                ) = (
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                )

            else:

                (
                    minimum,
                    maximum,
                    average,
                    median,
                    std,
                    q25,
                    q75,
                ) = stats

            entry.update(
                {
                    "type": "numeric",

                    "min": minimum,

                    "max": maximum,

                    "mean": (
                        round(
                            float(average),
                            4,
                        )
                        if average is not None
                        else None
                    ),

                    "median": (
                        float(median)
                        if median is not None
                        else None
                    ),

                    "std": (
                        round(
                            float(std),
                            4,
                        )
                        if std is not None
                        else None
                    ),

                    "q25": (
                        float(q25)
                        if q25 is not None
                        else None
                    ),

                    "q75": (
                        float(q75)
                        if q75 is not None
                        else None
                    ),
                }
            )

        else:

            entry["type"] = "categorical"

        profiles.append(entry)

    return profiles
# ============================================================
# HISTOGRAM
# ============================================================

def histogram(
    dataset: Dataset,
    column: str,
    bins: int = 20,
) -> dict:
    """
    Build a histogram for a numeric column.
    """

    con = dataset.con.cursor()

    q = _q(column)

    # --------------------------------------------------------
    # Minimum and maximum
    # --------------------------------------------------------

    result = con.execute(
        f"""
        SELECT
            MIN({q}),
            MAX({q})
        FROM main_table
        WHERE {q} IS NOT NULL
        """
    ).fetchone()

    if result is None:
        return {
            "column": column,
            "bin_edges": [],
            "counts": [],
        }

    minimum, maximum = result

    if minimum is None or maximum is None:
        return {
            "column": column,
            "bin_edges": [],
            "counts": [],
        }

    # --------------------------------------------------------
    # All values identical
    # --------------------------------------------------------

    if minimum == maximum:

        result = con.execute(
            f"""
            SELECT COUNT({q})
            FROM main_table
            WHERE {q} IS NOT NULL
            """
        ).fetchone()

        count = (
            int(result[0])
            if result and result[0] is not None
            else 0
        )

        return {
            "column": column,
            "bin_edges": [
                minimum,
                maximum,
            ],
            "counts": [
                count
            ],
        }

    # --------------------------------------------------------
    # Bin width
    # --------------------------------------------------------

    width = (
        float(maximum) -
        float(minimum)
    ) / bins

    if width <= 0:
        return {
            "column": column,
            "bin_edges": [],
            "counts": [],
        }

    # --------------------------------------------------------
    # Bucket query
    # --------------------------------------------------------

    rows = con.execute(
        f"""
        WITH bucketed AS (

            SELECT

                LEAST(
                    CAST(
                        FLOOR(
                            (
                                {q} -
                                {minimum}
                            )
                            / {width}
                        )
                        AS INTEGER
                    ),
                    {bins - 1}
                ) AS bucket

            FROM main_table

            WHERE {q} IS NOT NULL
        )

        SELECT
            bucket,
            COUNT(*) AS cnt

        FROM bucketed

        GROUP BY bucket

        ORDER BY bucket
        """
    ).fetchall()

    # --------------------------------------------------------
    # Fill empty buckets
    # --------------------------------------------------------

    counts = [0] * bins

    for bucket, count in rows:

        if bucket is None:
            continue

        bucket = int(bucket)

        if 0 <= bucket < bins:
            counts[bucket] = int(count)

    # --------------------------------------------------------
    # Bin edges
    # --------------------------------------------------------

    edges = [
        round(
            float(minimum) +
            i * width,
            6,
        )
        for i in range(
            bins + 1
        )
    ]

    return {
        "column": column,
        "bin_edges": edges,
        "counts": counts,
    }


# ============================================================
# TOP CATEGORIES
# ============================================================

def top_categories(
    dataset: Dataset,
    column: str,
    limit: int = 15,
) -> dict:
    """
    Return the most frequent categorical values.
    """

    con = dataset.con.cursor()

    q = _q(column)

    rows = con.execute(
        f"""
        SELECT
            {q} AS val,
            COUNT(*) AS cnt

        FROM main_table

        WHERE {q} IS NOT NULL

        GROUP BY {q}

        ORDER BY cnt DESC

        LIMIT {int(limit)}
        """
    ).fetchall()

    return {
        "column": column,

        "categories": [
            str(row[0])
            for row in rows
        ],

        "counts": [
            int(row[1])
            for row in rows
        ],
    }


# ============================================================
# MISSING VALUES CHART
# ============================================================

def missing_values_chart(
    dataset: Dataset,
) -> dict:
    """
    Return columns with missing values,
    ranked by missing percentage.
    """

    profiles = column_profiles(
        dataset
    )

    ranked = sorted(
        profiles,
        key=lambda item: item[
            "missing_pct"
        ],
        reverse=True,
    )

    ranked = [
        item
        for item in ranked
        if item["missing_pct"] > 0
    ][:25]

    return {
        "columns": [
            item["column"]
            for item in ranked
        ],

        "missing_pct": [
            item["missing_pct"]
            for item in ranked
        ],
    }


# ============================================================
# CATEGORICAL CHART COLUMNS
# ============================================================

def categorical_summary_columns(
    dataset: Dataset,
) -> list[str]:
    """
    Return categorical columns suitable
    for dashboard bar charts.

    High-cardinality columns are excluded.
    """

    con = dataset.con.cursor()

    keep = []

    for column in categorical_columns(
        dataset
    ):

        result = con.execute(
            f"""
            SELECT COUNT(
                DISTINCT {_q(column)}
            )
            FROM main_table
            """
        ).fetchone()

        if (
            result is None
            or result[0] is None
        ):
            distinct = 0
        else:
            distinct = int(
                result[0]
            )

        if (
            1 < distinct
            <= CATEGORICAL_MAX_CARDINALITY
        ):
            keep.append(column)

    return keep
# ============================================================
# CORRELATION MATRIX
# ============================================================

def correlation_matrix(
    dataset: Dataset,
) -> dict:
    """
    Calculate Pearson correlation between
    numeric columns.
    """

    columns = numeric_columns(
        dataset
    )

    # --------------------------------------------------------
    # Not enough numeric columns
    # --------------------------------------------------------

    if len(columns) < 2:

        return {
            "columns": columns,

            "matrix": [
                [1.0] * len(columns)
                for _ in columns
            ],
        }

    con = dataset.con.cursor()

    pairs = []
    expressions = []

    # --------------------------------------------------------
    # Build CORR expressions
    # --------------------------------------------------------

    for i, first in enumerate(columns):

        for second in columns[i:]:

            expressions.append(
                f"CORR("
                f"{_q(first)}, "
                f"{_q(second)}"
                f")"
            )

            pairs.append(
                (
                    first,
                    second,
                )
            )

    # --------------------------------------------------------
    # Execute
    # --------------------------------------------------------

    result = con.execute(
        f"""
        SELECT
            {", ".join(expressions)}
        FROM main_table
        """
    ).fetchone()

    if result is None:

        row = [
            None
            for _ in expressions
        ]

    else:

        row = result

    # --------------------------------------------------------
    # Build lookup
    # --------------------------------------------------------

    lookup = {}

    for (
        first,
        second,
    ), value in zip(
        pairs,
        row,
    ):

        if value is None:

            correlation = 0.0

        elif (
            isinstance(value, float)
            and math.isnan(value)
        ):

            correlation = 0.0

        else:

            correlation = round(
                float(value),
                4,
            )

        lookup[
            (first, second)
        ] = correlation

        lookup[
            (second, first)
        ] = correlation

    # --------------------------------------------------------
    # Build matrix
    # --------------------------------------------------------

    matrix = [
        [
            lookup[
                (first, second)
            ]
            for second in columns
        ]
        for first in columns
    ]

    return {
        "columns": columns,
        "matrix": matrix,
    }


# ============================================================
# SAMPLE ROWS
# ============================================================

def sample_rows(
    dataset: Dataset,
    limit: int = 50,
) -> list[dict]:
    """
    Return a small sample of dataset rows.
    """

    if not dataset.columns:
        return []

    # Protect against unreasonable limits.
    limit = max(
        1,
        min(
            int(limit),
            500,
        ),
    )

    con = dataset.con.cursor()

    columns_sql = ", ".join(
        _q(column)
        for column in dataset.columns
    )

    rows = con.execute(
        f"""
        SELECT {columns_sql}

        FROM main_table

        LIMIT {limit}
        """
    ).fetchall()

    return [
        dict(
            zip(
                dataset.columns,
                row,
            )
        )
        for row in rows
    ]


# ============================================================
# FULL REPORT DATA
# ============================================================

def build_full_report_data(
    dataset: Dataset,
) -> dict:
    """
    Aggregate all information required
    for the dashboard and PDF report.
    """

    num_cols = numeric_columns(
        dataset
    )

    cat_cols = categorical_summary_columns(
        dataset
    )

    return {
        # ----------------------------------------------------
        # Overview
        # ----------------------------------------------------

        "overview": overview_metrics(
            dataset
        ),

        # ----------------------------------------------------
        # Column statistics
        # ----------------------------------------------------

        "columns": column_profiles(
            dataset
        ),

        # ----------------------------------------------------
        # Numeric histograms
        # ----------------------------------------------------

        "histograms": [
            histogram(
                dataset,
                column,
            )
            for column in num_cols[:12]
        ],

        # ----------------------------------------------------
        # Categorical charts
        # ----------------------------------------------------

        "categorical_charts": [
            top_categories(
                dataset,
                column,
            )
            for column in cat_cols[:8]
        ],

        # ----------------------------------------------------
        # Missing values
        # ----------------------------------------------------

        "missing_chart": (
            missing_values_chart(
                dataset
            )
        ),

        # ----------------------------------------------------
        # Correlation
        # ----------------------------------------------------

        "correlation": (
            correlation_matrix(
                dataset
            )
            if len(num_cols) >= 2
            else None
        ),

        # ----------------------------------------------------
        # Sample data
        # ----------------------------------------------------

        "sample_rows": sample_rows(
            dataset,
            20,
        ),
    }# ============================================================
# PUBLIC API
# ============================================================

__all__ = [
    "overview_metrics",
    "column_profiles",
    "histogram",
    "top_categories",
    "missing_values_chart",
    "correlation_matrix",
    "categorical_summary_columns",
    "sample_rows",
    "build_full_report_data",
]