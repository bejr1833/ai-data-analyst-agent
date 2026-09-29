import os
import re
import numbers
from typing import Any

from dotenv import load_dotenv
from google import genai

from app.services.data_loader import Dataset
import time


# ============================================================
# GEMINI CONFIGURATION
# ============================================================

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY was not found. "
        "Make sure backend/.env contains GEMINI_API_KEY."
    )

client = genai.Client(
    api_key=GEMINI_API_KEY
)

MODEL = "gemini-3.6-flash"


# ============================================================
# COLUMN HELPERS
# ============================================================

def _q(column: str) -> str:
    """Safely quote a DuckDB column name."""
    return '"' + str(column).replace('"', '""') + '"'


# ============================================================
# SCHEMA
# ============================================================

def _schema_text(dataset: Dataset) -> str:
    """
    Build the dataset schema for Gemini using DuckDB metadata.

    The Dataset object stores the DuckDB connection and column names,
    rather than a pandas DataFrame or dtypes attribute.
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

    if not rows:
        raise ValueError("Dataset contains no columns.")

    lines = [
        f"Dataset: {dataset.filename}",
        f"Rows: {dataset.row_count}",
        "Columns:",
    ]

    for column_name, data_type in rows:
        lines.append(
            f'- "{column_name}" ({data_type})'
        )

    return "\n".join(lines)
# ============================================================
# CLEAN GEMINI SQL
# ============================================================

def _clean_sql(text: str) -> str:
    """
    Clean Gemini's SQL response.
    Supports SELECT and WITH queries.
    """

    if not text:
        raise ValueError(
            "Gemini returned an empty SQL response."
        )

    text = str(text).strip()

    # Remove opening markdown code fence
    text = re.sub(
        r"^\s*```(?:sql)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Remove closing markdown code fence
    text = re.sub(
        r"\s*```\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = text.strip()

    # Keep the query starting from SELECT or WITH
    match = re.search(
        r"\b(?:SELECT|WITH)\b",
        text,
        flags=re.IGNORECASE,
    )

    if match:
        text = text[match.start():]

    # Remove trailing semicolon
    text = text.rstrip(";").strip()

    if not text:
        raise ValueError(
            "Gemini returned an empty SQL query."
        )

    return text

def _conversation_text(
    conversation_history: list[dict] | None
) -> str:
    """
    Convert recent conversation history into a compact
    text block for Gemini.
    """

    if not conversation_history:
        return "No previous conversation."

    # Keep only the most recent 6 messages
    recent = conversation_history[-6:]

    lines = []

    for message in recent:

        if not isinstance(message, dict):
            continue

        role = message.get("role")
        text = message.get("text")

        if role not in {"user", "assistant"}:
            continue

        if not isinstance(text, str):
            continue

        text = text.strip()

        if not text:
            continue

        label = (
            "User"
            if role == "user"
            else "Assistant"
        )

        lines.append(
            f"{label}: {text}"
        )

    if not lines:
        return "No previous conversation."

    return "\n".join(lines)
# ============================================================
# GENERATE SQL WITH GEMINI
# ============================================================

def _generate_sql(
    dataset: Dataset,
    question: str,
    conversation_history: list[dict] | None = None,
) -> str:
    schema = _schema_text(dataset)

    conversation = _conversation_text(
    conversation_history
)

    prompt = f"""
You are the SQL engine for an AI Data Analyst application.

The user uploaded a dataset stored in DuckDB.

TABLE:
main_table

DATABASE SCHEMA:

{schema}

RECENT CONVERSATION:

{conversation}

CURRENT USER QUESTION:

{question}

TASK:
Generate exactly ONE valid DuckDB SQL query that answers
the user's question.

RULES:

1. Query only main_table.
2. Use only columns present in the schema.
3. The query must be read-only.
4. SELECT queries are allowed.
5. WITH ... SELECT queries are allowed.
6. Return exactly one SQL statement.
7. Use double quotes around column names.
8. Never use INSERT.
9. Never use UPDATE.
10. Never use DELETE.
11. Never use DROP.
12. Never use ALTER.
13. Never use CREATE.
14. Never use TRUNCATE.
15. Never use COPY.
16. Never use ATTACH.
17. Never use DETACH.
18. Never use INSTALL.
19. Never use LOAD.
20. Never use CALL.
21. Never use PRAGMA.
22. Never use EXPORT.
23. Never use IMPORT.
24. Never use multiple SQL statements.
25. Return SQL only.
26. Do not use markdown.
27. Do not explain your answer.

SQL:
"""

    try:
        interaction = client.interactions.create(
            model=MODEL,
            input=prompt,
        )

    except Exception as exc:
        raise RuntimeError(
            f"Gemini SQL generation failed: {exc}"
        ) from exc

    output_text = getattr(
        interaction,
        "output_text",
        None,
    )

    if not output_text:
        raise ValueError(
            "Gemini did not return SQL."
        )

    return _clean_sql(
        output_text
    )
# ============================================================
# SQL VALIDATION
# ============================================================

def _validate_sql(sql: str) -> None:
    """
    Validate Gemini-generated SQL before executing it.

    Only read-only SELECT/WITH queries against main_table
    are allowed.
    """

    if not sql:
        raise ValueError(
            "Generated SQL is empty."
        )

    normalized = sql.strip().lower()

    # --------------------------------------------------------
    # Only SELECT or WITH queries are allowed
    # --------------------------------------------------------

    if not (
        normalized.startswith("select")
        or normalized.startswith("with")
    ):
        raise ValueError(
            "Generated SQL must be a SELECT query."
        )

    # --------------------------------------------------------
    # Block dangerous SQL operations
    # --------------------------------------------------------

    forbidden_keywords = [
        "insert",
        "update",
        "delete",
        "drop",
        "alter",
        "create",
        "truncate",
        "copy",
        "attach",
        "detach",
        "install",
        "load",
        "call",
        "pragma",
        "export",
        "import",
    ]

    for keyword in forbidden_keywords:

        if re.search(
            rf"\b{re.escape(keyword)}\b",
            normalized,
        ):
            raise ValueError(
                "Generated SQL contains "
                f"forbidden operation: {keyword}"
            )

    # --------------------------------------------------------
    # Prevent multiple SQL statements
    # --------------------------------------------------------

    statements = [
        statement.strip()
        for statement in sql.split(";")
        if statement.strip()
    ]

    if len(statements) != 1:
        raise ValueError(
            "Only one SQL statement is allowed."
        )

    # --------------------------------------------------------
    # Ensure the uploaded dataset is queried
    # --------------------------------------------------------

    if not re.search(
        r"\bmain_table\b",
        normalized,
    ):
        raise ValueError(
            "Generated SQL must query main_table."
        )


# ============================================================
# EXECUTE SQL
# ============================================================

def _execute_sql(
    dataset: Dataset,
    sql: str,
):
    """
    Validate and execute Gemini-generated SQL
    against the DuckDB dataset.
    """

    # Validate before execution.
    _validate_sql(sql)

    try:
        result = dataset.con.execute(
            sql
        )

    except Exception as exc:
        raise RuntimeError(
            "DuckDB could not execute the "
            f"generated SQL: {exc}"
        ) from exc

    rows = result.fetchall()

    columns = [
        description[0]
        for description in result.description
    ]

    return columns, rows

# ============================================================
# SERIALIZATION
# ============================================================

def _serialize_value(value: Any):
    """
    Convert DuckDB / NumPy / Pandas values into
    JSON-friendly Python values.
    """

    if value is None:
        return None

    # Handle NumPy / Pandas scalar values
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass

    # Handle date / datetime values
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass

    # Handle bytes
    if isinstance(value, bytes):
        return value.decode(
            "utf-8",
            errors="replace",
        )

    return value


def _serialize_rows(
    columns,
    rows,
):
    """
    Convert database rows into dictionaries
    suitable for a JSON response.
    """

    serialized = []

    for row in rows:

        item = {}

        for index, column in enumerate(columns):

            item[column] = _serialize_value(
                row[index]
            )

        serialized.append(item)

    return serialized


# ============================================================
# DISPLAY VALUE
# ============================================================

def _display_value(value):
    """
    Format a value for the final natural-language answer.
    """

    value = _serialize_value(value)

    if value is None:
        return "N/A"

    if isinstance(value, bool):
        return "Yes" if value else "No"

    if isinstance(value, int):
        return f"{value:,}"

    if isinstance(value, float):

        if value.is_integer():
            return f"{int(value):,}"

        return f"{value:,.2f}"

    return str(value)


# ============================================================
# LOCAL ANSWER GENERATOR
# ============================================================

def _format_answer(
    question: str,
    columns,
    rows,
) -> str:
    """
    Convert SQL results into a human-readable answer.

    This is intentionally local so that we don't need
    a second Gemini API request.
    """

    # --------------------------------------------------------
    # No results
    # --------------------------------------------------------

    if not rows:

        return (
            "I couldn't find any matching "
            "results for that question."
        )

    # --------------------------------------------------------
    # Single value
    #
    # Example:
    # SELECT SUM("Sales") FROM main_table
    # --------------------------------------------------------

    if (
        len(rows) == 1
        and len(columns) == 1
    ):

        value = _display_value(
            rows[0][0]
        )

        return (
            f"The result is {value}."
        )

    # --------------------------------------------------------
    # Single row with multiple columns
    # --------------------------------------------------------

    if len(rows) == 1:

        parts = []

        for index, column in enumerate(
            columns
        ):

            value = _display_value(
                rows[0][index]
            )

            parts.append(
                f"{column}: {value}"
            )

        return (
            "The result is "
            + ", ".join(parts)
            + "."
        )

    # --------------------------------------------------------
    # Two-column grouped result
    # --------------------------------------------------------

    if len(columns) == 2:

        items = []

        for row in rows[:10]:

            category = _display_value(
                row[0]
            )

            value = _display_value(
                row[1]
            )

            items.append(
                f"{category}: {value}"
            )

        result_text = ", ".join(
            items
        )

        if len(rows) > 10:

            result_text += (
                f", and {len(rows) - 10:,} "
                "more results"
            )

        return (
            f"Here are the results by "
            f"{columns[0]}: "
            f"{result_text}."
        )

    # --------------------------------------------------------
    # Generic multi-row result
    # --------------------------------------------------------

    return (
        f"I found {len(rows):,} results. "
        f"The returned columns are: "
        f"{', '.join(columns)}."
    )
# ============================================================
# VISUALIZATION SELECTION
# ============================================================

# ============================================================
# VISUALIZATION SELECTION
# ============================================================

def _choose_visualization(
    columns,
    rows,
) -> dict:
    """
    Choose a visualization based on the SQL result.

    Supported frontend chart types:
        - bar
        - line
        - scatter
        - table

    Pie charts are intentionally not returned because the current
    AnalysisChart component does not render pie charts.
    """

    if not rows:
        return {
            "type": "table",
            "x": None,
            "y": None,
            "title": None,
        }

    if len(columns) == 1:
        return {
            "type": "table",
            "x": None,
            "y": columns[0],
            "title": None,
        }

    if len(columns) == 2:
        first_column = columns[0]
        second_column = columns[1]

        first_values = [
            row[0]
            for row in rows
            if row[0] is not None
        ]

        second_values = [
            row[1]
            for row in rows
            if row[1] is not None
        ]

        first_is_numeric = all(
            isinstance(value, numbers.Number)
            and not isinstance(value, bool)
            for value in first_values
        )

        second_is_numeric = all(
            isinstance(value, numbers.Number)
            and not isinstance(value, bool)
            for value in second_values
        )

        first_is_text = any(
            isinstance(value, str)
            for value in first_values
        )

        # Two numeric columns -> scatter.
        if first_is_numeric and second_is_numeric:
            return {
                "type": "scatter",
                "x": first_column,
                "y": second_column,
                "title": f"{first_column} vs {second_column}",
            }

        # Categorical + numeric -> bar.
        if first_is_text and second_is_numeric:
            return {
                "type": "bar",
                "x": first_column,
                "y": second_column,
                "title": f"{second_column} by {first_column}",
            }

        return {
            "type": "table",
            "x": None,
            "y": None,
            "title": None,
        }

    return {
        "type": "table",
        "x": None,
        "y": None,
        "title": None,
    }


def _choose_grouped_visualization(
    question: str,
    x_column: str,
    y_column: str,
    rows,
) -> dict:
    """
    Choose a chart for grouped/business results based on the
    user's question.
    """

    q = question.lower().strip()

    print("BUSINESS QUERY:", question)
    print("BUSINESS NORMALIZED:", q)

    readable_y = y_column.replace("_", " ").title()
    readable_x = x_column.replace("_", " ").title()

    # Detect aggregation from the user's question
    if any(word in q for word in ["average", "avg", "mean"]):
        operation_name = "Average"

    elif any(word in q for word in ["count", "number of", "how many"]):
        operation_name = "Count"

    elif any(word in q for word in [
        "maximum",
        "max",
        "highest",
        "largest",
    ]):
        operation_name = "Maximum"

    elif any(word in q for word in [
        "minimum",
        "min",
        "lowest", "bottom",
        "smallest",
    ]):
        operation_name = "Minimum"

    else:
        operation_name = "Total"

    if operation_name == "Count":
        metric_label = "Count"
    else:
        metric_label = f"{operation_name} {readable_y}"

    # Correlation / relationship questions -> scatter
    scatter_words = [
        "correlation",
        "correlate",
        "relationship",
        "relation",
        "versus",
        " vs ",
        "against",
    ]

    if any(word in q for word in scatter_words):
        numeric_pairs = 0

        for row in rows:
            if len(row) < 2:
                continue

            left = row[0]
            right = row[1]

            if (
                isinstance(left, numbers.Number)
                and not isinstance(left, bool)
                and isinstance(right, numbers.Number)
                and not isinstance(right, bool)
            ):
                numeric_pairs += 1

        if numeric_pairs > 0:
            return {
                "type": "scatter",
                "x": x_column,
                "y": y_column,
                "title": f"{readable_y} vs {readable_x}",
            }

    # Distribution / part-to-whole -> pie
    pie_words = [
        "distribution",
        "distribute",
        "share",
        "percentage of total",
        "percent of total",
        "proportion",
        "composition",
        "breakdown",
        "split",
        "contribution",
        "contributes",
        "revenue share",
        "sales share",
        "category share",
        "regional share",
    ]

    if any(word in q for word in pie_words):
        return {
            "type": "pie",
            "x": x_column,
            "y": y_column,
            "title": (
                f"{metric_label} "
                f"Distribution by {readable_x}"
            ),
        }

    # Trend / time questions -> line
    trend_words = [
        "trend",
        "over time",
        "time series",
        "monthly",
        "weekly",
        "daily",
        "yearly",
        "growth",
        "change over time",
        "historical",
    ]

    if any(word in q for word in trend_words):
        return {
            "type": "line",
            "x": x_column,
            "y": y_column,
            "title": f"{metric_label} over time",
        }

    # Default grouped visualization -> bar
    return {
        "type": "bar",
        "x": x_column,
        "y": y_column,
        "title": f"{metric_label} by {readable_x}",
    }

def _try_local_query(
    dataset,
    question: str,
):
    """
    Handle simple analytical questions locally using DuckDB.

    Returns:
        dict -> if the question can be handled locally
        None -> if Gemini should handle it
    """

    q = question.lower().strip()

    print("BUSINESS QUERY:", question)
    print("BUSINESS NORMALIZED:", q)

    # --------------------------------------------------------
    # ROW COUNT
    # --------------------------------------------------------

    if (
        "how many rows" in q
        or "number of rows" in q
        or "how many records" in q
        or "number of records" in q
        or "total records" in q
    ):

        sql = """
        SELECT COUNT(*) AS total_records
        FROM main_table
        """

        result = _execute_sql(
            dataset,
            sql,
        )

        columns, rows = result

        answer = (
            f"The dataset contains "
            f"{rows[0][0]:,} records."
        )

        return {
            "question": question,
            "type": "local_analysis",
            "answer": answer,
            "sql": sql.strip(),
            "columns": columns,
            "rows": _serialize_rows(
                columns,
                rows,
            ),
            "row_count": len(rows),
            "model": "local",
            "visualization": _choose_visualization(
                columns,
                rows,
            ),
        }

    # --------------------------------------------------------
    # COLUMN COUNT
    # --------------------------------------------------------

    if (
        "how many columns" in q
        or "number of columns" in q
    ):

        sql = """
        SELECT COUNT(*) AS total_columns
        FROM information_schema.columns
        WHERE table_name = 'main_table'
        """

        result = dataset.con.execute(sql)

        rows = result.fetchall()
        columns = [desc[0] for desc in result.description]

        answer = (
            f"The dataset contains "
            f"{rows[0][0]:,} columns."
        )

        return {
            "question": question,
            "type": "local_analysis",
            "answer": answer,
            "sql": sql.strip(),
            "columns": columns,
            "rows": _serialize_rows(
                columns,
                rows,
            ),
            "row_count": len(rows),
            "model": "local",
            "visualization": _choose_visualization(
                columns,
                rows,
            ),
        }

    # --------------------------------------------------------
    # SHOW COLUMNS
    # --------------------------------------------------------

    if (
        "show columns" in q
        or "list columns" in q
        or "what columns" in q
        or "column names" in q
    ):

        columns = [
            row[0]
            for row in dataset.con.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'main_table'
                ORDER BY ordinal_position
                """
            ).fetchall()
        ]

        rows = [
            (column,)
            for column in columns
        ]

        return {
            "question": question,
            "type": "local_analysis",
            "answer": (
                "The dataset contains the following columns: "
                + ", ".join(columns)
            ),
            "sql": None,
            "columns": ["column_name"],
            "rows": _serialize_rows(
                ["column_name"],
                rows,
            ),
            "row_count": len(rows),
            "model": "local",
            "visualization": {
                "type": "table",
                "x": None,
                "y": None,
                "title": "Dataset Columns",
            },
        }

    # --------------------------------------------------------
    # SAMPLE DATA
    # --------------------------------------------------------

    if (
        "show sample" in q
        or "sample data" in q
        or "show some rows" in q
        or "show first rows" in q
        or "show example rows" in q
    ):

        sql = """
        SELECT *
        FROM main_table
        LIMIT 10
        """

        columns, rows = _execute_sql(
            dataset,
            sql,
        )

        return {
            "question": question,
            "type": "local_analysis",
            "answer": "Here are the first 10 rows of the dataset.",
            "sql": sql.strip(),
            "columns": columns,
            "rows": _serialize_rows(
                columns,
                rows,
            ),
            "row_count": len(rows),
            "model": "local",
            "visualization": {
                "type": "table",
                "x": None,
                "y": None,
                "title": "Sample Data",
            },
        }

    # --------------------------------------------------------
    # NOT HANDLED LOCALLY
    # --------------------------------------------------------

    return None

# ============================================================
# MAIN AI ANALYST
# ============================================================

import time

# ============================================================
# LOCAL NUMERIC ANALYSIS
# ============================================================

# ============================================================
# LOCAL NUMERIC ANALYSIS
# ============================================================
def _try_business_insight_query(
    dataset: Dataset,
    question: str,
) -> dict | None:
    """
    Handles business-oriented questions such as:

        Which region has the highest sales?
        Which region has the lowest sales?
        Which product generated the most revenue?
        What is the top product by revenue?
        What is the best-performing region?
    """

    q = question.lower().strip()

    print("BUSINESS QUERY:", question)
    print("BUSINESS NORMALIZED:", q)

    # --------------------------------------------------------
    # Detect ranking / comparison intent
    # --------------------------------------------------------

    highest_words = [
        "highest",
        "maximum",
        "max",
        "largest",
        "top",
        "best",
        "most",
        "ranked",
        "ranking",
        "rank",
    ]

    lowest_words = [
        "lowest", "bottom",
        "minimum",
        "min",
        "smallest",
        "worst",
        "least",
    ]

    is_highest = any(word in q for word in highest_words)
    is_lowest = any(word in q for word in lowest_words)

    print("BUSINESS FLAGS:", is_highest, is_lowest)

    if not is_highest and not is_lowest:
        return None

    # Explicit top-N / bottom-N requests must return N rows rather than
    # falling through to the single-winner business insight behavior.
    top_n_match = re.search(r"\b(?:top|bottom)\s+(\d+)\b", q)

    is_rank_request = any(
        word in q
        for word in ["ranked", "ranking", "rank"]
    )

    if top_n_match:
        requested_n = int(top_n_match.group(1))
        requested_n = max(1, min(requested_n, 50))
    elif is_rank_request:
        requested_n = None
    else:
        requested_n = 1

    # --------------------------------------------------------
    # Get columns
    # --------------------------------------------------------

    schema_rows = dataset.con.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'main_table'
        ORDER BY ordinal_position
        """
    ).fetchall()

    if not schema_rows:
        return None

    columns = [
        row[0]
        for row in schema_rows
    ]

    # --------------------------------------------------------
    # Find grouping dimension
    # --------------------------------------------------------

    group_column = None

    if "region" in q and "region" in columns:
        group_column = "region"

    elif "product" in q and "product" in columns:
        group_column = "product"

    elif (
        "area" in q
        and "region" in columns
    ):
        group_column = "region"

    elif (
        "location" in q
        and "region" in columns
    ):
        group_column = "region"

    elif (
        "category" in q
        and "product" in columns
    ):
        group_column = "product"

    if group_column is None:
        return None

    # --------------------------------------------------------
    # Find metric
    # --------------------------------------------------------

    metric_aliases = {
        "sales": "revenue",
        "sale": "revenue",
        "revenue": "revenue",
        "units": "units_sold",
        "units sold": "units_sold",
        "price": "unit_price",
        "marketing": "marketing_spend",
        "marketing spend": "marketing_spend",
        "rating": "customer_rating",
        "customer rating": "customer_rating",
        "returns": "returns",
    }

    metric_column = None

    for phrase, actual_column in metric_aliases.items():

        if (
            phrase in q
            and actual_column in columns
        ):
            metric_column = actual_column
            break

    if metric_column is None:
        return None

    # --------------------------------------------------------
    # Determine aggregation
    # --------------------------------------------------------

    if any(
        word in q
        for word in ["average", "avg", "mean"]
    ):
        aggregation = "AVG"
        aggregation_label = "average"

    elif any(
        word in q
        for word in ["count", "number of", "how many"]
    ):
        aggregation = "COUNT"
        aggregation_label = "count"

    elif any(
        word in q
        for word in ["maximum", "max", "highest", "largest"]
    ):
        aggregation = "MAX"
        aggregation_label = "maximum"

    elif any(
        word in q
        for word in ["minimum", "min", "lowest", "bottom", "smallest"]
    ):
        aggregation = "MIN"
        aggregation_label = "minimum"

    else:
        aggregation = "SUM"
        aggregation_label = "total"

    # --------------------------------------------------------
    # Build SQL
    # --------------------------------------------------------

    group_identifier = (
        '"'
        + group_column.replace('"', '""')
        + '"'
    )

    metric_identifier = (
        '"'
        + metric_column.replace('"', '""')
        + '"'
    )

    if is_lowest and not is_highest:

        order = "ASC"
        direction_text = "lowest"

    else:

        order = "DESC"
        direction_text = "highest"

    limit_clause = (
        f"LIMIT {requested_n}"
        if requested_n is not None
        else ""
    )

    if aggregation == "COUNT":
        aggregate_expression = f'COUNT({metric_identifier})'
    else:
        aggregate_expression = (
            f'{aggregation}('
            f'TRY_CAST({metric_identifier} AS DOUBLE)'
            f')'
        )

    sql = f"""
    SELECT
        {group_identifier} AS "{group_column}",
        {aggregate_expression} AS "{metric_column}"
    FROM main_table
    GROUP BY {group_identifier}
    ORDER BY "{metric_column}" {order}
    {limit_clause}
    """

    # --------------------------------------------------------
    # Execute
    # --------------------------------------------------------

    try:

        result_columns, rows = _execute_sql(
            dataset,
            sql,
        )

    except Exception as exc:

        print(
            "Business insight query failed:",
            repr(exc),
        )

        return None

    if not rows:
        return None

    # --------------------------------------------------------
    # Extract result
    # --------------------------------------------------------

    readable_metric = metric_column.replace(
        "_",
        " ",
    )

    readable_group = group_column.replace(
        "_",
        " ",
    )

    # --------------------------------------------------------
    # Natural-language answer
    # --------------------------------------------------------

    if is_rank_request or (requested_n is not None and requested_n > 1):
        ranked_lines = []
        for index, row in enumerate(rows, start=1):
            group_value = _display_value(row[0])
            metric_value = _display_value(row[1])
            ranked_lines.append(
                f"{index}. {group_value}: {metric_value}"
            )

        ranking_metric_label = (
            f"{aggregation_label} {readable_metric}"
            if aggregation != "SUM"
            else readable_metric
        )

        answer = (
            f"{'Ranked' if is_rank_request else direction_text.title()} {len(rows)} {readable_group}s "
            f"by {ranking_metric_label}:\n"
            + "\n".join(ranked_lines)
        )
    else:
        group_value = _display_value(rows[0][0])
        metric_value = _display_value(rows[0][1])
        answer = (
            f"{group_value} has the {direction_text} "
            f"total {readable_metric} among all "
            f"{readable_group}s, with "
            f"{metric_value}."
        )

    # --------------------------------------------------------
    # Visualization
    # --------------------------------------------------------

    visualization_metric_label = (
        f"{aggregation_label} {readable_metric}"
        if aggregation != "SUM"
        else readable_metric
    )

    if is_rank_request:
        visualization_title = (
            f"{visualization_metric_label.title()} ranked by "
            f"{readable_group}"
        )
    elif is_lowest:
        visualization_title = (
            f"Bottom {requested_n} {readable_group}s by "
            f"{visualization_metric_label}"
        )
    else:
        visualization_title = (
            f"Top {requested_n} {readable_group}s by "
            f"{visualization_metric_label}"
        )

    visualization = {
        "type": "bar",
        "x": group_column,
        "y": metric_column,
        "y_label": visualization_metric_label,
        "title": visualization_title,
    }
    # --------------------------------------------------------
    # Return
    # --------------------------------------------------------

    return {
        "question": question,
        "type": "business_insight",
        "answer": answer,
        "sql": sql.strip(),
        "columns": result_columns,
        "rows": _serialize_rows(
            result_columns,
            rows,
        ),
        "row_count": len(rows),
        "model": "local",
        "visualization": visualization,
    }

def _try_grouped_query(
    dataset: Dataset,
    question: str,
) -> dict | None:
    """
    Handle questions such as:

        Show total sales by region
        Show average revenue by product
        Show total units sold by region
        Show average rating by product
        Show sales distribution by region

    Uses DuckDB directly without Gemini.
    """

    q = question.lower().strip()

    print("BUSINESS QUERY:", question)
    print("BUSINESS NORMALIZED:", q)

    # --------------------------------------------------------
    # --------------------------------------------------------
    # Detect comparison questions
    # --------------------------------------------------------

    comparison_mode = False
    comparison_values = []

    if "compare" in q and " and " in q:

        # Pattern: compare ... between North and South
        if " between " in q:
            comparison_part = q.split(" between ", 1)[1]
            comparison_part = comparison_part.split(" and ", 1)

            if len(comparison_part) == 2:
                comparison_values = [
                    comparison_part[0].strip(" .?!"),
                    comparison_part[1].strip(" .?!"),
                ]

                comparison_values = [
                    re.sub(
                        r"\s+(?:regions?|products?|categories?|areas?|locations?)$",
                        "",
                        value,
                        flags=re.IGNORECASE,
                    ).strip()
                    for value in comparison_values
                ]

        # Pattern: compare ... of North and South
        elif " of " in q:
            comparison_part = q.split(" of ", 1)[1]
            comparison_part = comparison_part.split(" and ", 1)

            if len(comparison_part) == 2:
                comparison_values = [
                    comparison_part[0].strip(" .?!"),
                    comparison_part[1].strip(" .?!"),
                ]

                comparison_values = [
                    re.sub(
                        r"\s+(?:regions?|products?|categories?|areas?|locations?)$",
                        "",
                        value,
                        flags=re.IGNORECASE,
                    ).strip()
                    for value in comparison_values
                ]

        if len(comparison_values) == 2:
            comparison_values = [
                re.sub(
                    r"\s+(?:regions?|products?|categories?|areas?|locations?)$",
                    "",
                    value,
                    flags=re.IGNORECASE,
                ).strip()
                for value in comparison_values
            ]
            comparison_mode = True

    # Normal grouped questions require "by".
    # Comparison questions use "between X and Y" or "of X and Y".
    if " by " not in q and not comparison_mode:
        return None

    # --------------------------------------------------------
    # Get dataset columns
    # --------------------------------------------------------

    schema_rows = dataset.con.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'main_table'
        ORDER BY ordinal_position
        """
    ).fetchall()

    if not schema_rows:
        return None

    columns = [
        row[0]
        for row in schema_rows
    ]

    # --------------------------------------------------------
    # Find grouping column
    # --------------------------------------------------------

    group_aliases = {
        "area": "region",
        "location": "region",
        "territory": "region",
        "item": "product",
        "category": "product",
    }

    group_column = None

    for alias, actual_column in group_aliases.items():

        if alias in q and actual_column in columns:
            group_column = actual_column
            break

    # Exact column matching
    if group_column is None:

        for column in columns:

            column_lower = column.lower()

            if (
                f"by {column_lower}" in q
                or f"by {column_lower.replace('_', ' ')}" in q
            ):
                group_column = column
                break

    # --------------------------------------------------------
    # Infer grouping column for comparison questions
    # --------------------------------------------------------

    if group_column is None and comparison_mode and len(comparison_values) == 2:

        for column in columns:

            identifier = (
                '"'
                + column.replace('"', '""')
                + '"'
            )

            try:
                distinct_rows = dataset.con.execute(
                    f"""
                    SELECT DISTINCT {identifier}
                    FROM main_table
                    WHERE {identifier} IS NOT NULL
                    LIMIT 1000
                    """
                ).fetchall()
            except Exception:
                continue

            distinct_values = {
                str(row[0]).strip().lower()
                for row in distinct_rows
            }

            if all(
                value.lower() in distinct_values
                for value in comparison_values
            ):
                group_column = column
                break

    # --------------------------------------------------------
    # Detect grouping column from comparison values
    # --------------------------------------------------------

    if group_column is None and comparison_mode and len(comparison_values) == 2:

        for column in columns:

            try:
                query = (
                    'SELECT DISTINCT "'
                    + column.replace('"', '""')
                    + '" FROM main_table '
                    + 'WHERE "'
                    + column.replace('"', '""')
                    + '" IS NOT NULL LIMIT 1000'
                )

                distinct_rows = dataset.con.execute(query).fetchall()

            except Exception:
                continue

            distinct_values = {
                str(row[0]).strip().lower()
                for row in distinct_rows
            }

            if all(
                value.lower() in distinct_values
                for value in comparison_values
            ):
                group_column = column
                break

    if group_column is None:
        return None

    # --------------------------------------------------------
    # Determine metric
    # --------------------------------------------------------

    metric_aliases = {
        "revenue": ["revenue"],

        # If the dataset has a real "sales" column,
        # use it. Otherwise fall back to revenue.
        "sales": ["sales", "revenue"],
        "sale": ["sales", "revenue"],

        "units sold": ["units_sold"],
        "units": ["units_sold"],
        "unit": ["units_sold"],

        "price": ["unit_price"],
        "unit price": ["unit_price"],

        "marketing": ["marketing_spend"],
        "marketing spend": ["marketing_spend"],
        "marketing spending": ["marketing_spend"],

        "rating": ["customer_rating"],
        "customer rating": ["customer_rating"],

        "returns": ["returns"],
        "return": ["returns"],
    }

    metric_column = None

    for phrase, possible_columns in metric_aliases.items():

        if phrase not in q:
            continue

        for actual_column in possible_columns:

            if actual_column in columns:
                metric_column = actual_column
                break

        if metric_column is not None:
            break

    # --------------------------------------------------------
    # Try direct column matching
    # --------------------------------------------------------

    if metric_column is None:

        for column in columns:

            column_text = column.lower()
            readable_column = column_text.replace("_", " ")

            if (
                column_text in q
                or readable_column in q
            ):
                metric_column = column
                break

    if metric_column is None:
        return None

    # --------------------------------------------------------
    # Determine aggregation
    # --------------------------------------------------------

    if any(
        word in q
        for word in [
            "average",
            "avg",
            "mean",
        ]
    ):
        aggregation = "AVG"
        operation_name = "average"

    elif any(
        word in q
        for word in [
            "count",
            "number of",
            "how many",
        ]
    ):
        aggregation = "COUNT"
        operation_name = "count"

    elif any(
        word in q
        for word in [
            "maximum",
            "max",
            "highest",
            "largest",
        ]
    ):
        aggregation = "MAX"
        operation_name = "maximum"

    elif any(
        word in q
        for word in [
            "minimum",
            "min",
            "lowest", "bottom",
            "smallest",
        ]
    ):
        aggregation = "MIN"
        operation_name = "minimum"

    else:
        aggregation = "SUM"
        operation_name = "total"

    # --------------------------------------------------------
    # Build safe SQL identifiers
    # --------------------------------------------------------

    group_identifier = (
        '"'
        + group_column.replace('"', '""')
        + '"'
    )

    metric_identifier = (
        '"'
        + metric_column.replace('"', '""')
        + '"'
    )

    # --------------------------------------------------------
    # Build comparison filter
    # --------------------------------------------------------

    where_clause = ""

    if comparison_mode and len(comparison_values) == 2:

        escaped_values = [
            value.replace("'", "''")
            for value in comparison_values
        ]

        value_list = ", ".join(
            f"'{value}'"
            for value in escaped_values
        )

        where_clause = (
            f"WHERE LOWER(CAST({group_identifier} AS VARCHAR)) "
            f"IN ({value_list})"
        )

    # --------------------------------------------------------
    # Build SQL
    # --------------------------------------------------------

    if aggregation == "COUNT":

        sql = f"""
        SELECT
            {group_identifier} AS "{group_column}",
            COUNT({metric_identifier}) AS "count"
        FROM main_table
        {where_clause}
        GROUP BY {group_identifier}
        ORDER BY "count" DESC
        """

    else:

        sql = f"""
        SELECT
            {group_identifier} AS "{group_column}",
            {aggregation}(
                TRY_CAST(
                    {metric_identifier}
                    AS DOUBLE
                )
            ) AS "{metric_column}"
        FROM main_table
        {where_clause}
        GROUP BY {group_identifier}
        ORDER BY "{metric_column}" DESC
        """

    # --------------------------------------------------------
    # Execute query
    # --------------------------------------------------------

    try:

        result_columns, rows = _execute_sql(
            dataset,
            sql,
        )

    except Exception as exc:

        print(
            "Grouped query failed:",
            repr(exc),
        )

        return None

    if not rows:
        return None

    # --------------------------------------------------------
    # Format answer
    # --------------------------------------------------------

    answer_lines = []

    for row in rows:

        if len(row) < 2:
            continue

        group_value = _display_value(
            row[0]
        )

        metric_value = _display_value(
            row[1]
        )

        answer_lines.append(
            f"{group_value}: {metric_value}"
        )

    # --------------------------------------------------------
    # Comparison-specific answer
    # --------------------------------------------------------

    if comparison_mode and len(rows) == 2:

        first_group = _display_value(rows[0][0])
        first_value = float(rows[0][1])

        second_group = _display_value(rows[1][0])
        second_value = float(rows[1][1])

        difference = abs(first_value - second_value)

        if first_value > second_value:
            higher_group = first_group
        elif second_value > first_value:
            higher_group = second_group
        else:
            higher_group = None

        readable_metric = metric_column.replace("_", " ")

        if higher_group is None:
            comparison_summary = (
                f"Both {first_group} and {second_group} "
                f"have the same {readable_metric}."
            )
        else:
            lower_group = (
                second_group
                if higher_group == first_group
                else first_group
            )

            comparison_summary = (
                f"{higher_group} generated "
                f"{difference:,.0f} more {readable_metric} "
                f"than {lower_group}."
            )

        answer = (
            f"{readable_metric.title()} comparison between "
            f"{first_group} and {second_group}:\n"
            + "\n".join(answer_lines)
            + "\n\n"
            + comparison_summary
        )

    else:

        answer = (
            f"The {operation_name} of "
            f"{metric_column.replace('_', ' ')} "
            f"by {group_column.replace('_', ' ')} is:\n"
            + "\n".join(answer_lines)
        )

    # --------------------------------------------------------
    # Visualization
    # --------------------------------------------------------

    visualization = _choose_grouped_visualization(
        question=question,
        x_column=group_column,
        y_column=(
            "count"
            if aggregation == "COUNT"
            else metric_column
        ),
        rows=rows,
    )

    # Use an aggregation-aware comparison chart title.
    if comparison_mode and len(comparison_values) == 2:

        if aggregation == "AVG":
            comparison_title = (
                f"Average {metric_column.replace('_', ' ').title()} Comparison"
            )
        elif aggregation == "MAX":
            comparison_title = (
                f"Maximum {metric_column.replace('_', ' ').title()} Comparison"
            )
        elif aggregation == "MIN":
            comparison_title = (
                f"Minimum {metric_column.replace('_', ' ').title()} Comparison"
            )
        elif aggregation == "COUNT":
            comparison_title = (
                f"Count Comparison"
            )
        else:
            comparison_title = (
                f"{metric_column.replace('_', ' ').title()} Comparison"
            )

        visualization["title"] = (
            f"{comparison_title}: "
            f"{comparison_values[0].title()} vs "
            f"{comparison_values[1].title()}"
        )

    # --------------------------------------------------------
    # Return result
    # --------------------------------------------------------

    return {
        "question": question,
        "type": "local_grouped_analysis",
        "answer": answer,
        "sql": sql.strip(),
        "columns": result_columns,
        "rows": _serialize_rows(
            result_columns,
            rows,
        ),
        "row_count": len(rows),
        "model": "local",
        "visualization": visualization,
    }

def _try_percentage_query(
    dataset,
    question: str,
) -> dict | None:
    """
    Handle common percentage/rate questions locally with DuckDB.

    Supports:
      - Return-rate questions
      - Grouped percentage-of-total questions such as:
        "What percentage of revenue comes from each region?"
    """
    q = question.lower().strip()

    print("BUSINESS QUERY:", question)
    print("BUSINESS NORMALIZED:", q)

    percentage_intent = (
        "percentage" in q
        or "percent" in q
        or "return rate" in q
    )

    if not percentage_intent:
        return None

    columns = list(getattr(dataset, "columns", []) or [])
    lower_columns = {
        str(col).lower(): col
        for col in columns
    }

    def quote_identifier(name):
        return '"' + str(name).replace('"', '""') + '"'

    # --------------------------------------------------------
    # GROUPED PERCENTAGE-OF-TOTAL ANALYSIS
    # Example:
    # "What percentage of revenue comes from each region?"
    # --------------------------------------------------------

    grouped_words = (
        "each" in q
        or "by" in q
        or "per" in q
        or "from each" in q
        or "contribution" in q
        or "contributes" in q
        or "share" in q
        or "breakdown" in q
        or "composition" in q
        or "distribution" in q
    )

    metric_column = None

    # Prefer an explicitly mentioned numeric metric.
    for keyword, column_name in [
        ("revenue", "revenue"),
        ("sales", "sales"),
        ("profit", "profit"),
        ("amount", "amount"),
        ("units sold", "units_sold"),
        ("units", "units"),
    ]:
        if keyword in q and column_name in lower_columns:
            metric_column = lower_columns[column_name]
            break

    # Try to identify a grouping/category column.
    group_column = None

    if "region" in q and "region" in lower_columns:
        group_column = lower_columns["region"]
    elif "category" in q and "category" in lower_columns:
        group_column = lower_columns["category"]
    elif "product" in q and "product" in lower_columns:
        group_column = lower_columns["product"]
    elif "segment" in q and "segment" in lower_columns:
        group_column = lower_columns["segment"]
    elif "country" in q and "country" in lower_columns:
        group_column = lower_columns["country"]
    elif "city" in q and "city" in lower_columns:
        group_column = lower_columns["city"]
    elif "department" in q and "department" in lower_columns:
        group_column = lower_columns["department"]

    if (
        grouped_words
        and metric_column is not None
        and group_column is not None
    ):
        metric_sql = quote_identifier(metric_column)
        group_sql = quote_identifier(group_column)

        sql = f"""
            WITH grouped AS (
                SELECT
                    {group_sql} AS group_value,
                    SUM(
                        TRY_CAST({metric_sql} AS DOUBLE)
                    ) AS metric_value
                FROM main_table
                WHERE {group_sql} IS NOT NULL
                GROUP BY {group_sql}
            ),
            totals AS (
                SELECT
                    SUM(metric_value) AS total_value
                FROM grouped
            )
            SELECT
                group_value,
                metric_value,
                CASE
                    WHEN total_value = 0 THEN 0
                    ELSE
                        (metric_value * 100.0)
                        / total_value
                END AS percentage
            FROM grouped
            CROSS JOIN totals
            ORDER BY metric_value DESC
        """

        started = time.perf_counter()

        try:
            rows_raw = dataset.con.execute(sql).fetchall()
        except Exception as exc:
            print(
                "Grouped percentage query failed:",
                repr(exc),
            )
            return None

        duration_ms = round(
            (time.perf_counter() - started) * 1000,
            2,
        )

        if not rows_raw:
            return None

        rows = [
            {
                str(group_column): row[0],
                str(metric_column): (
                    float(row[1])
                    if row[1] is not None
                    else 0.0
                ),
                "percentage": (
                    float(row[2])
                    if row[2] is not None
                    else 0.0
                ),
            }
            for row in rows_raw
        ]

        total_value = sum(
            row[str(metric_column)]
            for row in rows
        )

        percentage_parts = [
            f"{row[str(group_column)]}: {row['percentage']:.2f}%"
            for row in rows
        ]

        answer = (
            f"{metric_column.title()} share by "
            f"{str(group_column)}: "
            + ", ".join(percentage_parts)
            + "."
        )

        return {
            "question": question,
            "type": "percentage_analysis",
            "answer": answer,
            "sql": sql.strip(),
            "columns": [
                str(group_column),
                str(metric_column),
                "percentage",
            ],
            "rows": rows,
            "row_count": len(rows),
            "model": "local",
            "visualization": {
                "type": "pie",
                "x": str(group_column),
                "y": "percentage",
                "title": (
                    f"{metric_column.title()} "
                    f"Contribution by {str(group_column).title()}"
                ),
            },
            "duration_ms": duration_ms,
        }

    # --------------------------------------------------------
    # EXISTING RETURN-RATE ANALYSIS
    # --------------------------------------------------------

    numerator = None
    denominator = None

    if (
        ("returned" in q or "return" in q)
        and ("unit" in q or "units" in q)
    ):
        numerator = (
            lower_columns.get("returns")
            or lower_columns.get("returned")
        )
        denominator = (
            lower_columns.get("units_sold")
            or lower_columns.get("units")
            or lower_columns.get("total_units")
        )

    if numerator is None and "return rate" in q:
        numerator = (
            lower_columns.get("returns")
            or lower_columns.get("returned")
        )
        denominator = (
            lower_columns.get("units_sold")
            or lower_columns.get("units")
            or lower_columns.get("total_units")
        )

    if numerator is None or denominator is None:
        return None

    numerator_sql = quote_identifier(numerator)
    denominator_sql = quote_identifier(denominator)

    sql = f"""
        SELECT
            (
                SUM(
                    TRY_CAST({numerator_sql} AS DOUBLE)
                ) * 100.0
            ) / NULLIF(
                SUM(
                    TRY_CAST({denominator_sql} AS DOUBLE)
                ),
                0
            ) AS percentage
        FROM main_table
    """

    started = time.perf_counter()

    try:
        row = dataset.con.execute(sql).fetchone()
    except Exception as exc:
        print(
            "Percentage query failed:",
            repr(exc),
        )
        return None

    duration_ms = round(
        (time.perf_counter() - started) * 1000,
        2,
    )

    if not row or row[0] is None:
        return None

    percentage = float(row[0])

    answer = (
        f"{percentage:.2f}% of units were returned."
    )

    return {
        "question": question,
        "type": "percentage_analysis",
        "answer": answer,
        "sql": sql.strip(),
        "columns": ["percentage"],
        "rows": [
            {
                "percentage": percentage,
            }
        ],
        "row_count": 1,
        "model": "local",
        "visualization": {
            "type": "metric",
            "y": "percentage",
            "title": "Percentage of Units Returned",
        },
        "duration_ms": duration_ms,
    }

def _try_numeric_query(
    dataset,
    question: str,
):
    """
    Handle simple numeric aggregation questions locally.

    Examples:
        TOTAL SALES
        TOTAL REVENUE
        AVERAGE SALES
        AVERAGE REVENUE
        MAX REVENUE
        MIN UNITS SOLD
    """

    q = question.lower().strip()

    print("BUSINESS QUERY:", question)
    print("BUSINESS NORMALIZED:", q)

    # --------------------------------------------------------
    # STEP 1 ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â Determine operation
    # --------------------------------------------------------

    if (
        "average" in q
        or "avg" in q
        or "mean" in q
    ):
        operation = "AVG"

    elif (
        "total" in q
        or "sum" in q
    ):
        operation = "SUM"

    elif (
        "maximum" in q
        or "max" in q
        or "highest" in q
        or "largest" in q
    ):
        operation = "MAX"

    elif (
        "minimum" in q
        or "min" in q
        or "lowest" in q
        or "smallest" in q
    ):
        operation = "MIN"

    elif (
        "count" in q
        or "how many" in q
    ):
        operation = "COUNT"

    else:
        return None

    # --------------------------------------------------------
    # STEP 2 ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â Get actual dataset columns
    # --------------------------------------------------------

    schema_rows = dataset.con.execute(
        """
        SELECT
            column_name,
            data_type
        FROM information_schema.columns
        WHERE table_name = 'main_table'
        ORDER BY ordinal_position
        """
    ).fetchall()

    if not schema_rows:
        return None

    # --------------------------------------------------------
    # STEP 3 ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â Find column
    # --------------------------------------------------------

    selected_column = None

    # --------------------------------------------------------
    # Business-language aliases
    # --------------------------------------------------------

    column_aliases = {
        "marketing spending": "marketing_spend",
        "marketing spend": "marketing_spend",
        "marketing cost": "marketing_spend",
        "marketing": "marketing_spend",

        "customer rating": "customer_rating",
        "rating": "customer_rating",

        "unit price": "unit_price",
        "price per unit": "unit_price",
        "unit_price": "unit_price",
        "price": "unit_price",

        "units sold": "units_sold",
        "units_sold": "units_sold",
        "quantity": "units_sold",
        "qty": "units_sold",
        "units": "units_sold",

        "revenue": "revenue",
        "sales": "revenue",
        "sale": "revenue",
        "income": "revenue",
        "earnings": "revenue",

        "returns": "returns",
        "return": "returns",
    }

    # Match longer, more specific phrases before shorter aliases.
    for alias, actual_column in sorted(
        column_aliases.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if alias in q:
            for column_name, data_type in schema_rows:
                if column_name.lower() == actual_column.lower():
                    selected_column = column_name
                    break

        if selected_column is not None:
            break

    # --------------------------------------------------------
    # Try exact column name
    # --------------------------------------------------------

    if selected_column is None:

        for column_name, data_type in schema_rows:

            if column_name.lower() in q:

                selected_column = column_name
                break

    # --------------------------------------------------------
    # Try normalized column name
    # --------------------------------------------------------

    if selected_column is None:

        normalized_question = re.sub(
            r"[^a-z0-9]+",
            "",
            q,
        )

        for column_name, data_type in schema_rows:

            normalized_column = re.sub(
                r"[^a-z0-9]+",
                "",
                column_name.lower(),
            )

            if (
                normalized_column
                and normalized_column
                in normalized_question
            ):

                selected_column = column_name
                break

    # --------------------------------------------------------
    # Try word-level matching
    # --------------------------------------------------------

    if selected_column is None:

        question_words = set(
            re.findall(
                r"[a-zA-Z0-9]+",
                q,
            )
        )

        ignored_words = {
            "what",
            "is",
            "the",
            "total",
            "average",
            "avg",
            "mean",
            "sum",
            "maximum",
            "minimum",
            "max",
            "min",
            "highest",
            "lowest", "bottom",
            "largest",
            "smallest",
            "of",
            "for",
            "give",
            "me",
            "calculate",
            "show",
        }

        question_words -= ignored_words

        for column_name, data_type in schema_rows:

            column_words = re.findall(
                r"[a-zA-Z0-9]+",
                column_name.lower(),
            )

            for word in column_words:

                if (
                    len(word) >= 2
                    and word in question_words
                ):

                    selected_column = column_name
                    break

            if selected_column is not None:
                break

    # --------------------------------------------------------
    # Column not found
    # --------------------------------------------------------

    if selected_column is None:

        print(
            "LOCAL NUMERIC: column not found for:",
            question,
        )

        print(
            "Available columns:",
            [
                row[0]
                for row in schema_rows
            ],
        )

        return None

    print(
        "LOCAL NUMERIC: selected column:",
        selected_column,
    )

    # --------------------------------------------------------
    # STEP 4 ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â Safely quote column
    # --------------------------------------------------------

    quoted_column = (
        '"'
        + selected_column.replace(
            '"',
            '""',
        )
        + '"'
    )

    # --------------------------------------------------------
    # STEP 5 ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â Build SQL
    # --------------------------------------------------------

    if operation == "COUNT":

        sql = f"""
        SELECT
            COUNT({quoted_column}) AS count
        FROM main_table
        """

    else:

        sql = f"""
        SELECT
            {operation}(
                TRY_CAST(
                    {quoted_column}
                    AS DOUBLE
                )
            ) AS result
        FROM main_table
        """

    # --------------------------------------------------------
    # STEP 6 ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â Execute locally
    # --------------------------------------------------------

    try:

        columns, rows = _execute_sql(
            dataset,
            sql,
        )

    except Exception as e:

        print(
            "LOCAL NUMERIC SQL ERROR:",
            repr(e),
        )

        return None

    if not rows:
        return None

    value = rows[0][0]

    if value is None:
        return None

    # --------------------------------------------------------
    # STEP 7 ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â Format answer
    # --------------------------------------------------------

    operation_names = {
        "SUM": "total",
        "AVG": "average",
        "MIN": "minimum",
        "MAX": "maximum",
        "COUNT": "count",
    }

    operation_name = operation_names[
        operation
    ]

    display_value = _display_value(
        value
    )

    answer = (
        f"The {operation_name} of "
        f"{selected_column} is "
        f"{display_value}."
    )

    # --------------------------------------------------------
    # STEP 8 ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â Return local result
    # --------------------------------------------------------

    return {
        "question": question,
        "type": "local_analysis",
        "answer": answer,
        "sql": sql.strip(),
        "columns": columns,
        "rows": _serialize_rows(
            columns,
            rows,
        ),
        "row_count": len(rows),
        "model": "local",
        "visualization": {
            "type": "metric",
            "x": None,
            "y": None,
            "title": f"{operation_name.title()} {selected_column.replace('_', ' ')}",
            "value": value,
            "label": selected_column.replace("_", " "),
        },
    }



def _try_trend_query(dataset, question: str) -> dict | None:
    """
    Handle time-series trend questions locally using DuckDB.

    Examples:
        Show revenue trend over time
        Show sales trend
        Revenue trend by date
    """

    q = question.lower().strip()

    print("BUSINESS QUERY:", question)
    print("BUSINESS NORMALIZED:", q)

    trend_keywords = [
        "trend",
        "over time",
        "time series",
        "historical trend",
        "change over time",
        "growth over time",
        "daily trend",
        "weekly trend",
        "monthly trend",
        "yearly trend",
    ]

    if not any(keyword in q for keyword in trend_keywords):
        return None

    # Get dataset schema.
    try:
        schema_rows = dataset.con.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'main_table'
            ORDER BY ordinal_position
            """
        ).fetchall()
    except Exception as exc:
        print("Trend schema lookup failed:", repr(exc))
        return None

    if not schema_rows:
        return None

    columns = [row[0] for row in schema_rows]

    # Find a date/time column.
    date_column = None

    for column_name, data_type in schema_rows:
        dtype = str(data_type).upper()
        if (
            "DATE" in dtype
            or "TIMESTAMP" in dtype
            or "DATETIME" in dtype
        ):
            date_column = column_name
            break

    if date_column is None:
        for candidate in ["date", "datetime", "timestamp", "time", "day"]:
            for column in columns:
                if column.lower() == candidate:
                    date_column = column
                    break
            if date_column:
                break

    if date_column is None:
        return None

    # Detect the requested metric.
    metric_aliases = {
        "revenue": [
            "revenue", "sales", "sale", "income", "earnings"
        ],
        "units_sold": [
            "units_sold", "units", "quantity", "qty"
        ],
        "unit_price": [
            "unit_price", "price"
        ],
        "marketing_spend": [
            "marketing_spend", "marketing", "marketing cost"
        ],
        "customer_rating": [
            "customer_rating", "rating"
        ],
        "returns": [
            "returns", "return"
        ],
    }

    metric_column = None

    for metric_name, aliases in metric_aliases.items():
        if metric_name in q or any(alias in q for alias in aliases):
            for column in columns:
                if column.lower() in aliases:
                    metric_column = column
                    break
        if metric_column:
            break

    # Default to revenue when the user says "trend" without another metric.
    if metric_column is None:
        for column in columns:
            if column.lower() == "revenue":
                metric_column = column
                break

    if metric_column is None:
        return None

    safe_date = date_column.replace('"', '""')
    safe_metric = metric_column.replace('"', '""')

    sql = f"""
        SELECT
            TRY_CAST("{safe_date}" AS DATE) AS "date",
            SUM(
                TRY_CAST("{safe_metric}" AS DOUBLE)
            ) AS "{safe_metric}"
        FROM main_table
        WHERE TRY_CAST("{safe_date}" AS DATE) IS NOT NULL
        GROUP BY TRY_CAST("{safe_date}" AS DATE)
        ORDER BY TRY_CAST("{safe_date}" AS DATE) ASC
    """.strip()

    try:
        result_columns, result_rows = _execute_sql(dataset, sql)
    except Exception as exc:
        print("Trend query failed:", repr(exc))
        return None

    if not result_rows:
        return None

    serialized_rows = _serialize_rows(result_columns, result_rows)

    # The first result column is always normalized to "date".
    # The second is the selected metric.
    metric_result_column = result_columns[1]

    answer_items = []
    for row in serialized_rows[:10]:
        date_value = row.get("date")
        metric_value = row.get(metric_result_column)
        answer_items.append(
            f"{date_value}: {_display_value(metric_value)}"
        )

    answer = (
        "Here are the results by date: "
        + ", ".join(answer_items)
    )

    if len(serialized_rows) > 10:
        answer += f", and {len(serialized_rows) - 10:,} more results."

    visualization = {
        "type": "line",
        "x": "date",
        "y": metric_result_column,
        "title": (
            f"{metric_result_column.replace('_', ' ').title()} "
            "Trend Over Time"
        ),
    }

    return {
        "question": question,
        "type": "trend",
        "answer": answer,
        "sql": sql,
        "columns": result_columns,
        "rows": serialized_rows,
        "row_count": len(serialized_rows),
        "model": "local",
        "visualization": visualization,
    }

# ============================================================
# CONTEXTUAL FOLLOW-UP ANALYSIS
# ============================================================


def _try_main_insight_query(
    dataset: Dataset,
    question: str,
) -> dict | None:
    """
    Generate a compact set of dataset-level business insights locally.

    The calculations are performed by DuckDB so large datasets do not need
    to be sent to Gemini.
    """

    q = question.lower().strip()

    print("BUSINESS QUERY:", question)
    print("BUSINESS NORMALIZED:", q)

    insight_phrases = [
        "main insight",
        "key insight",
        "main takeaway",
        "key takeaway",
        "most important business insight",
        "most important insight",
        "important business insight",
        "business insight",
        "give me an insight",
        "give me insights",
        "what can you conclude",
        "what does this tell us",
        "what does that tell us",
    ]

    if not any(phrase in q for phrase in insight_phrases):
        return None

    try:
        schema_rows = dataset.con.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'main_table'
            ORDER BY ordinal_position
            """
        ).fetchall()

        columns = [row[0] for row in schema_rows]

        if not columns:
            return None

        insights = []
        result_rows = []

        # --------------------------------------------------------
        # Revenue insights
        # --------------------------------------------------------

        revenue_column = next(
            (
                column
                for column in ["revenue", "sales"]
                if column in columns
            ),
            None,
        )

        if revenue_column:

            revenue_id = (
                '"'
                + revenue_column.replace('"', '""')
                + '"'
            )

            total_sql = f"""
            SELECT
                SUM(
                    TRY_CAST(
                        {revenue_id} AS DOUBLE
                    )
                ) AS total_revenue
            FROM main_table
            """

            total_row = dataset.con.execute(
                total_sql
            ).fetchone()

            total_revenue = (
                float(total_row[0])
                if total_row and total_row[0] is not None
                else 0.0
            )

            # Prefer region, then product.
            for group_column in ["region", "product"]:

                if group_column not in columns:
                    continue

                group_id = (
                    '"'
                    + group_column.replace('"', '""')
                    + '"'
                )

                sql = f"""
                SELECT
                    {group_id} AS "{group_column}",
                    SUM(
                        TRY_CAST(
                            {revenue_id} AS DOUBLE
                        )
                    ) AS revenue
                FROM main_table
                WHERE {group_id} IS NOT NULL
                GROUP BY {group_id}
                ORDER BY revenue DESC
                """

                rows = dataset.con.execute(sql).fetchall()

                if not rows:
                    continue

                top_group = _display_value(rows[0][0])
                top_value = float(rows[0][1])

                share = (
                    top_value / total_revenue * 100
                    if total_revenue
                    else 0.0
                )

                label = group_column.replace("_", " ")

                insights.append(
                    f"{top_group} has the highest total "
                    f"{revenue_column.replace('_', ' ')} among "
                    f"{label}s, at {top_value:,.0f} "
                    f"({share:.1f}% of total revenue)."
                )

                result_rows.extend(
                    [
                        {
                            "insight_type": f"top_{group_column}",
                            "dimension": top_group,
                            "value": top_value,
                        }
                    ]
                )

        # --------------------------------------------------------
        # Return-rate insight
        # --------------------------------------------------------

        returns_column = next(
            (
                column
                for column in ["returns", "returned"]
                if column in columns
            ),
            None,
        )

        units_column = next(
            (
                column
                for column in [
                    "units_sold",
                    "units",
                    "total_units",
                ]
                if column in columns
            ),
            None,
        )

        if returns_column and units_column:

            returns_id = (
                '"'
                + returns_column.replace('"', '""')
                + '"'
            )

            units_id = (
                '"'
                + units_column.replace('"', '""')
                + '"'
            )

            return_sql = f"""
            SELECT
                (
                    SUM(
                        TRY_CAST(
                            {returns_id} AS DOUBLE
                        )
                    ) * 100.0
                ) / NULLIF(
                    SUM(
                        TRY_CAST(
                            {units_id} AS DOUBLE
                        )
                    ),
                    0
                ) AS return_percentage
            FROM main_table
            """

            return_row = dataset.con.execute(
                return_sql
            ).fetchone()

            if return_row and return_row[0] is not None:

                return_percentage = float(return_row[0])

                insights.append(
                    f"Approximately {return_percentage:.2f}% "
                    f"of units were returned."
                )

                result_rows.append(
                    {
                        "insight_type": "return_rate",
                        "dimension": "returned units",
                        "value": return_percentage,
                    }
                )

        # --------------------------------------------------------
        # Final result
        # --------------------------------------------------------

        if not insights:
            return None

        answer = "Main insights from the dataset:\n\n" + "\n".join(
            f"Ã¢â‚¬Â¢ {insight}"
            for insight in insights
        )

        return {
            "question": question,
            "type": "business_insight",
            "answer": answer,
            "sql": None,
            "columns": [
                "insight_type",
                "dimension",
                "value",
            ],
            "rows": result_rows,
            "row_count": len(result_rows),
            "model": "local",
            "visualization": {
                "type": "table",
                "title": "Main Dataset Insights",
            },
        }

    except Exception as exc:
        print(
            "Main insight query failed:",
            repr(exc),
        )
        return None


def _normalize_conversation_history(conversation_history: list[dict] | None) -> list[dict]:
    """Normalize chat history from text/content/answer based clients."""
    if not isinstance(conversation_history, list):
        return []
    normalized = []
    for message in conversation_history:
        if not isinstance(message, dict):
            continue
        item = dict(message)
        text_value = item.get("text") or item.get("content")
        if not text_value and item.get("role") == "assistant":
            text_value = item.get("answer")
        if isinstance(text_value, list):
            parts = []
            for part in text_value:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict):
                    value = part.get("text") or part.get("content")
                    if value:
                        parts.append(str(value))
            text_value = " ".join(parts)
        if text_value is not None:
            item["text"] = str(text_value)
        if item.get("role") == "assistant" and isinstance(item.get("result"), dict):
            result = item["result"]
            if not item.get("rows") and isinstance(result.get("rows"), list):
                item["rows"] = result["rows"]
            if not item.get("visualization") and result.get("visualization") is not None:
                item["visualization"] = result["visualization"]
            if not item.get("sql") and result.get("sql"):
                item["sql"] = result["sql"]
            if not item.get("resultType") and result.get("type"):
                item["resultType"] = result["type"]
        normalized.append(item)
    return normalized


def _try_contextual_followup(
    dataset,
    question: str,
    conversation_history: list[dict] | None = None,
) -> dict | None:
    """
    Handle conversational follow-up questions locally.

    Examples:
        User: What is the total revenue?
        User: Can you explain that?

        User: Show revenue by region.
        User: Which one is highest?

        User: What is the correlation between revenue
               and marketing spend?
        User: What does that mean?

    This prevents simple contextual questions from unnecessarily
    falling back to Gemini.
    """

    if not conversation_history:
        return None

    if not isinstance(question, str):
        return None

    q = question.lower().strip()

    print("BUSINESS QUERY:", question)
    print("BUSINESS NORMALIZED:", q)

    # --------------------------------------------------------
    # Follow-up detection
    # --------------------------------------------------------

    # "Main insight" is a dataset-level analytical request, not an
    # explanation of the previous result. It is handled by the dedicated
    # main-insight tool in the agent planner.
    main_insight_phrases = [
        "main insight",
        "key insight",
        "main takeaway",
        "key takeaway",
        "give me an insight",
        "give me insights",
        "what can you conclude",
        "what does this tell us",
        "what does that tell us",
    ]

    if any(phrase in q for phrase in main_insight_phrases):
        return None

    explanation_phrases = [
        "explain that",
        "explain this",
        "explain it",
        "explain these results",
        "explain the results",
        "explain those results",
        "what do these results mean",
        "what do the results mean",
        "what does this result mean",
        "can you explain",
        "could you explain",
        "please explain",
        "what does that mean",
        "what does this mean",
        "what does it mean",
        "tell me more",
        "what is the main insight",
        "what's the main insight",
        "what is the key insight",
        "what's the key insight",
        "main insight",
        "key insight",
        "give me an insight",
        "what can you conclude",
        "what can we conclude",
        "what does this tell us",
        "what does that tell us",
        "summarize these results",
        "summarize the results",
        "give me a summary of these results",
        "explain the trend",
        "explain this trend",
        "what does this trend mean",
        "describe the trend",
        "what is the trend telling us",
        "why is that",
        "why is this",
        "why",
        "how did you calculate that",
        "how was that calculated",
        "how did you get that",
    ]

    ranking_phrases = [
        "which one is highest",
        "which is highest",
        "which one is the highest",
        "which is the highest",
        "what is highest",
        "which one is lowest",
        "which is lowest",
        "which one is the lowest",
        "which is the lowest",
        "what is lowest",
        "which category contributes the most",
        "which category contributes most",
        "which contributes the most",
        "which category has the highest",
        "which category is highest",
    ]

    is_explanation = any(
        phrase in q
        for phrase in explanation_phrases
    )

    is_ranking = any(
        phrase in q
        for phrase in ranking_phrases
    )

    if not is_explanation and not is_ranking:
        return None

    # --------------------------------------------------------
    # Find the most recent assistant result
    # --------------------------------------------------------

    previous_assistant = None

    for message in reversed(conversation_history):
        if not isinstance(message, dict):
            continue

        if message.get("role") == "assistant":
            previous_assistant = message
            break

    if not previous_assistant:
        return None

    previous_text = (
        str(
            previous_assistant.get("text")
            or previous_assistant.get("content")
            or previous_assistant.get("answer")
            or ""
        )
        .strip()
    )

    previous_rows = previous_assistant.get("rows")

    if not isinstance(previous_rows, list):
        previous_rows = []

    previous_visualization = (
        previous_assistant.get("visualization")
    )

    previous_result_type = (
        previous_assistant.get("resultType")
    )

    # --------------------------------------------------------
    # Nothing useful to explain
    # --------------------------------------------------------

    if not previous_text and not previous_rows:
        return None

    # --------------------------------------------------------
    # FAST-PATH CONTEXTUAL EXPLANATION
    # --------------------------------------------------------
    # Simple explanation follow-ups must never reach the SQL/Gemini
    # fallback. Return the previous result immediately using only the
    # conversation payload. This avoids expensive dataset work and also
    # makes the follow-up resilient if a previous SQL field is missing.
    # --------------------------------------------------------
    # Scenario / projection follow-up
    # --------------------------------------------------------
    scenario_text = previous_text.lower()

    scenario_markers = [
        "projected",
        "projection",
        "increase by",
        "decrease by",
        "after a",
        "if revenue",
        "if sales",
        "scenario",
    ]

    if is_explanation and any(
        marker in scenario_text
        for marker in scenario_markers
    ):
        answer = (
            "This follows directly from the previous scenario analysis. "
            f"{previous_text}"
        )

        return {
            "question": question,
            "type": "contextual_followup",
            "answer": answer,
            "sql": previous_assistant.get("sql"),
            "columns": previous_assistant.get("columns") or [],
            "rows": previous_rows,
            "row_count": len(previous_rows),
            "model": "local",
            "visualization": previous_visualization,
        }

    if is_explanation:
        # Explain a previous single-value analysis locally.
        answer = ""

        if len(previous_rows) == 1 and isinstance(previous_rows[0], dict):
            row = previous_rows[0]

            numeric_values = [
                (key, value)
                for key, value in row.items()
                if isinstance(value, (int, float))
                and not isinstance(value, bool)
            ]

            if numeric_values:
                metric_key, metric_value = numeric_values[0]
                readable_metric = str(metric_key).replace("_", " ")

                previous_sql = str(
                    previous_assistant.get("sql") or ""
                ).strip()

                import re

                sum_match = re.search(
                    r'SUM\s*\(\s*(?:TRY_CAST\s*\(\s*)?["`]?([A-Za-z_][A-Za-z0-9_]*)',
                    previous_sql,
                    re.IGNORECASE,
                )
                avg_match = re.search(
                    r'AVG\s*\(\s*(?:TRY_CAST\s*\(\s*)?["`]?([A-Za-z_][A-Za-z0-9_]*)', 
                    previous_sql,
                    re.IGNORECASE,
                )

                correlation_context = (
                    "correlation" in previous_text.lower()
                    or "correlation" in str(previous_result_type).lower()
                    or (
                        isinstance(previous_visualization, dict)
                        and str(previous_visualization.get("type", "")).lower()
                        in {"scatter", "correlation"}
                    )
                )

                if correlation_context:
                    if metric_value > 0.8:
                        strength = "very strong"
                    elif metric_value > 0.6:
                        strength = "strong"
                    elif metric_value > 0.4:
                        strength = "moderate"
                    elif metric_value > 0.2:
                        strength = "weak"
                    else:
                        strength = "very weak"

                    direction = (
                        "positive"
                        if metric_value > 0
                        else "negative"
                        if metric_value < 0
                        else "no"
                    )

                    answer = (
                        f"A correlation of {metric_value:.2f} indicates a "
                        f"{strength} {direction} linear relationship between "
                        f"the variables in the previous analysis. "
                    )

                    if metric_value > 0:
                        answer += (
                            "In this dataset, higher values of one variable "
                            "tend to be associated with higher values of the "
                            "other variable. "
                        )
                    elif metric_value < 0:
                        answer += (
                            "In this dataset, higher values of one variable "
                            "tend to be associated with lower values of the "
                            "other variable. "
                        )
                    else:
                        answer += (
                            "The variables show little to no linear "
                            "relationship in this dataset. "
                        )

                    answer += (
                        "Correlation indicates association, not causation, "
                        "so this result alone does not establish that one "
                        "variable causes changes in the other."
                    )

                elif sum_match:
                    source_column = sum_match.group(1)
                    readable_source = source_column.replace("_", " ")
                    answer = (
                        f"The total {readable_source} is "
                        f"{metric_value:,.0f}. "
                        f"This was calculated by summing all values in "
                        f"the '{readable_source}' column across the dataset. "
                        f"The SQL operation used was "
                        f"SUM({source_column}), which produced "
                        f"{metric_value:,.0f}."
                    )
                elif avg_match:
                    source_column = avg_match.group(1)
                    readable_source = source_column.replace("_", " ")
                    answer = (
                        f"The average {readable_source} is "
                        f"{metric_value:,.2f}. "
                        f"This was calculated using the average of the "
                        f"'{readable_source}' column."
                    )
                else:
                    answer = (
                        f"The previous analysis calculated "
                        f"{readable_metric} as {metric_value:,.2f}. "
                        f"This value came directly from the previous "
                        f"analysis result."
                    )

        # Explain multi-row trend results using the previous rows.
        if not answer and (
            "trend" in q
            or (
                isinstance(previous_visualization, dict)
                and previous_visualization.get("type") in {"line", "forecast"}
            )
            or previous_result_type in {"trend", "forecast"}
        ) and previous_rows:
            numeric_points = []

            for row in previous_rows:
                if not isinstance(row, dict):
                    continue

                numeric_values = [
                    value
                    for value in row.values()
                    if isinstance(value, (int, float))
                    and not isinstance(value, bool)
                ]

                if numeric_values:
                    numeric_points.append(float(numeric_values[-1]))

            if numeric_points:
                first_value = numeric_points[0]
                last_value = numeric_points[-1]
                highest_value = max(numeric_points)
                lowest_value = min(numeric_points)

                if last_value > first_value:
                    direction = "an upward overall movement"
                elif last_value < first_value:
                    direction = "a downward overall movement"
                else:
                    direction = "little overall change"

                answer = (
                    f"The trend shows {direction} across the available "
                    f"{len(numeric_points):,} observations. "
                    f"The values range from {lowest_value:,.0f} to "
                    f"{highest_value:,.0f}. "
                    f"The first observed value is {first_value:,.0f}, "
                    f"while the latest observed value is {last_value:,.0f}."
                )

        if not answer:
            answer = (
                "The previous analysis returned: "
                f"{previous_text}"
            )

            if previous_rows:
                answer += (
                    f" The analysis returned {len(previous_rows):,} "
                    "result row"
                    + ("" if len(previous_rows) == 1 else "s")
                    + "."
                )

        return {
            "question": question,
            "type": "contextual_followup",
            "answer": answer,
            "sql": previous_assistant.get("sql"),
            "columns": [],
            "rows": [],
            "row_count": 0,
            "model": "local",
            "visualization": None,
        }

    # For a generic explanation request, preserve the previous analytical
    # result instead of allowing the normal SQL/local-query engine to
    # reinterpret the phrase as a brand-new question. This is especially
    # important for multi-row results such as data-quality tables.
    # Single-row numeric results continue through the detailed calculation
    # branch below.
    if is_explanation and len(previous_rows) != 1:
        answer = (
            "The previous result came from the analysis immediately before "
            "this question. In particular, I found: "
            f"{previous_text}"
        )
        return {
            "question": question,
            "type": "contextual_followup",
            "answer": answer,
            "sql": previous_assistant.get("sql"),
            "columns": [],
            "rows": previous_rows,
            "row_count": len(previous_rows),
            "model": "local",
            "visualization": previous_visualization,
        }

    # --------------------------------------------------------
    # Ranking follow-up
    # --------------------------------------------------------

    if is_ranking and previous_rows:

        valid_rows = [
            row
            for row in previous_rows
            if isinstance(row, dict)
        ]

        if not valid_rows:
            return None

        numeric_candidates = []

        for row in valid_rows:

            for key, value in row.items():

                if isinstance(value, bool):
                    continue

                if isinstance(value, (int, float)):
                    numeric_candidates.append(
                        (row, key, float(value))
                    )

        if not numeric_candidates:
            return None

        # Prefer a value column rather than an identifier.
        preferred = [
            item
            for item in numeric_candidates
            if any(
                keyword in item[1].lower()
                for keyword in [
                    "revenue",
                    "sales",
                    "total",
                    "amount",
                    "value",
                    "units",
                ]
            )
        ]

        candidates = (
            preferred
            if preferred
            else numeric_candidates
        )

        if "highest" in q or "most" in q:

            selected = max(
                candidates,
                key=lambda item: item[2],
            )

            direction = "highest"

        else:

            selected = min(
                candidates,
                key=lambda item: item[2],
            )

            direction = "lowest"

        row, value_column, value = selected

        category_columns = [
            key
            for key in row.keys()
            if key != value_column
        ]

        if category_columns:
            category_column = category_columns[0]
            category_value = row.get(
                category_column
            )

            answer = (
                f"The {direction} value is "
                f"{value:,.2f}, belonging to "
                f"{category_column.replace('_', ' ')} "
                f"'{category_value}'."
            )

        else:
            answer = (
                f"The {direction} value is "
                f"{value:,.2f}."
            )

        return {
            "question": question,
            "type": "contextual_followup",
            "answer": answer,
            "sql": previous_assistant.get("sql"),
            "columns": list(row.keys()),
            "rows": previous_rows,
            "row_count": len(previous_rows),
            "model": "local",
            "visualization": previous_visualization,
        }

    # --------------------------------------------------------
    # Explanation follow-up
    # --------------------------------------------------------

    if is_explanation:

        # ----------------------------------------------------
        # Scenario / projection follow-up
        # ----------------------------------------------------
        scenario_text = previous_text.lower()

        scenario_markers = [
            "projected",
            "projection",
            "increase by",
            "decrease by",
            "after a",
            "if revenue",
            "if sales",
            "scenario",
        ]

        if any(
            marker in scenario_text
            for marker in scenario_markers
        ):
            answer = (
                "This follows directly from the previous scenario analysis. "
                f"{previous_text}"
            )

            return {
                "question": question,
                "type": "contextual_followup",
                "answer": answer,
                "sql": previous_assistant.get("sql"),
                "columns": previous_assistant.get("columns") or [],
                "rows": previous_rows,
                "row_count": len(previous_rows),
                "model": "local",
                "visualization": previous_visualization,
            }

        # ----------------------------------------------------
        # Single numeric result
        # ----------------------------------------------------


        if len(previous_rows) == 1:

            row = previous_rows[0]

            if isinstance(row, dict):

                numeric_values = []

                for key, value in row.items():

                    if isinstance(value, bool):
                        continue

                    if isinstance(
                        value,
                        (int, float),
                    ):
                        numeric_values.append(
                            (key, value)
                        )

                if numeric_values:

                    metric_key, metric_value = numeric_values[0]

                    previous_sql = str(
                        previous_assistant.get("sql")
                        or ""
                    ).strip()

                    # Always initialize this variable because the SQL may
                    # already be present in conversation history.
                    source_column = None

                    if not previous_sql:
                        # The frontend may send the previous numeric result
                        # without preserving its SQL. In that case, `result`
                        # is only an alias and is NOT the source metric.
                        # Recover the metric from the previous user question
                        # and the actual dataset schema before constructing SQL.
                        source_column = None

                        try:
                            schema_columns = [
                                row[0]
                                for row in dataset.con.execute(
                                    """
                                    SELECT column_name
                                    FROM information_schema.columns
                                    WHERE table_name = 'main_table'
                                    ORDER BY ordinal_position
                                    """
                                ).fetchall()
                            ]
                        except Exception:
                            schema_columns = []

                        history_text = " ".join(
                            str(message.get("text") or message.get("content") or "")
                            for message in conversation_history
                            if isinstance(message, dict)
                            and message.get("role") == "user"
                        ).lower()

                        # Prefer exact dataset-column matches, including
                        # readable forms such as `units sold`.
                        for column in schema_columns:
                            column_lower = str(column).lower()
                            readable_column = column_lower.replace("_", " ")
                            if (
                                column_lower in history_text
                                or readable_column in history_text
                            ):
                                source_column = column
                                break

                        # Business-language aliases used by this application.
                        if source_column is None:
                            aliases = {
                                "sales": "revenue",
                                "sale": "revenue",
                                "income": "revenue",
                                "earnings": "revenue",
                                "units": "units_sold",
                                "unit": "units_sold",
                                "price": "unit_price",
                                "marketing": "marketing_spend",
                                "marketing spend": "marketing_spend",
                                "rating": "customer_rating",
                                "customer rating": "customer_rating",
                                "returns": "returns",
                            }

                            for phrase, actual_column in aliases.items():
                                if phrase in history_text and actual_column in schema_columns:
                                    source_column = actual_column
                                    break

                        # Last-resort fallback: only use the returned key if
                        # it is an actual dataset column, never the SQL alias
                        # `result`.
                        if source_column is None and metric_key in schema_columns:
                            source_column = metric_key

                        if source_column is None:
                            source_column = metric_key

                        previous_sql = (
                            f'SELECT SUM("{source_column}") AS result '
                            f'FROM main_table'
                        )

                    # If SQL was already preserved, recover the real source
                    # column from the SQL. If SQL was reconstructed above,
                    # source_column already contains the inferred metric.
                    sql_source_column = None

                    # Recover the real source column from SQL.
                    # Example: SUM("revenue") AS result -> revenue
                    column_match = re.search(
                        r'SUM\(\s*"([^"]+)"\s*\)'
                        r'|AVG\(\s*"([^"]+)"\s*\)'
                        r'|MAX\(\s*"([^"]+)"\s*\)'
                        r'|MIN\(\s*"([^"]+)"\s*\)'
                        r'|COUNT\(\s*"([^"]+)"\s*\)',
                        previous_sql,
                        flags=re.IGNORECASE | re.DOTALL,
                    )

                    if column_match:
                        sql_source_column = next(
                            (group for group in column_match.groups() if group),
                            None,
                        )

                    # Handle SQL such as SUM(TRY_CAST("revenue" AS DOUBLE)).
                    if not sql_source_column:
                        cast_match = re.search(
                            r'TRY_CAST\(\s*"([^"]+)"\s+AS\s+DOUBLE\s*\)',
                            previous_sql,
                            flags=re.IGNORECASE | re.DOTALL,
                        )

                        if cast_match:
                            sql_source_column = cast_match.group(1)


                    # Never treat a generic SQL alias such as `result` or
                    # `count` as the actual dataset metric. If the SQL only
                    # exposes that alias, recover the metric from the user's
                    # previous question and the dataset schema.
                    generic_aliases = {
                        "result",
                        "count",
                        "value",
                        "total",
                    }

                    if sql_source_column and sql_source_column.lower() not in generic_aliases:
                        source_column = sql_source_column
                    else:
                        try:
                            schema_columns = [
                                row[0]
                                for row in dataset.con.execute(
                                    """
                                    SELECT column_name
                                    FROM information_schema.columns
                                    WHERE table_name = 'main_table'
                                    ORDER BY ordinal_position
                                    """
                                ).fetchall()
                            ]
                        except Exception:
                            schema_columns = []

                        history_text = " ".join(
                            str(message.get("text") or message.get("content") or "")
                            for message in conversation_history
                            if isinstance(message, dict)
                            and message.get("role") == "user"
                        ).lower()

                        inferred_column = None

                        # Exact dataset column names first.
                        for column in schema_columns:
                            column_lower = str(column).lower()
                            readable_column = column_lower.replace("_", " ")
                            if (
                                column_lower in history_text
                                or readable_column in history_text
                            ):
                                inferred_column = column
                                break

                        # Then business-language aliases.
                        if inferred_column is None:
                            aliases = {
                                "sales": "revenue",
                                "sale": "revenue",
                                "income": "revenue",
                                "earnings": "revenue",
                                "units": "units_sold",
                                "unit": "units_sold",
                                "price": "unit_price",
                                "marketing": "marketing_spend",
                                "marketing spend": "marketing_spend",
                                "rating": "customer_rating",
                                "customer rating": "customer_rating",
                                "returns": "returns",
                            }

                            for phrase, actual_column in aliases.items():
                                if phrase in history_text and actual_column in schema_columns:
                                    inferred_column = actual_column
                                    break

                        if inferred_column is not None:
                            source_column = inferred_column

                    if not source_column or str(source_column).lower() in generic_aliases:
                        # Last safe fallback: use a real dataset column only.
                        if metric_key in schema_columns:
                            source_column = metric_key
                        elif "revenue" in schema_columns:
                            source_column = "revenue"
                        else:
                            source_column = metric_key

                    readable_metric = source_column.replace(
                        "_", " "
                    ).strip()

                    sql_upper = previous_sql.upper()

                    if "SUM(" in sql_upper:
                        operation = "SUM"
                    elif "AVG(" in sql_upper:
                        operation = "AVG"
                    elif "MAX(" in sql_upper:
                        operation = "MAX"
                    elif "MIN(" in sql_upper:
                        operation = "MIN"
                    elif "COUNT(" in sql_upper:
                        operation = "COUNT"
                    else:
                        operation = "UNKNOWN"

                    formatted_value = _display_value(metric_value)

                    if operation == "SUM":
                        try:
                            row_count = dataset.row_count
                        except Exception:
                            row_count = None

                        answer = (
                            f"The total {readable_metric} is "
                            f"{formatted_value}. This was calculated "
                            f"by summing all values in the "
                            f"'{source_column}' column"
                        )

                        if row_count:
                            answer += (
                                f" across the {row_count:,} records "
                                f"in your dataset."
                            )
                        else:
                            answer += " in your dataset."

                        answer += (
                            f" The SQL operation used was "
                            f"SUM({source_column}), which produced "
                            f"{formatted_value}."
                        )

                    elif operation == "AVG":
                        answer = (
                            f"The average {readable_metric} is "
                            f"{formatted_value}. This was calculated "
                            f"by taking the average of the "
                            f"'{source_column}' values in your dataset."
                        )

                    elif operation == "MAX":
                        answer = (
                            f"The maximum {readable_metric} is "
                            f"{formatted_value}. This is the largest "
                            f"value found in the '{source_column}' column."
                        )

                    elif operation == "MIN":
                        answer = (
                            f"The minimum {readable_metric} is "
                            f"{formatted_value}. This is the smallest "
                            f"value found in the '{source_column}' column."
                        )

                    elif operation == "COUNT":
                        answer = (
                            f"The count is {formatted_value}. The system "
                            f"counted the matching records in your dataset."
                        )

                    else:
                        answer = (
                            f"The previous calculation returned "
                            f"{formatted_value} for {readable_metric}."
                        )

                    return {
                        "question": question,
                        "type": "contextual_followup",
                        "answer": answer,
                        "sql": previous_sql,
                        "columns": list(row.keys()),
                        "rows": previous_rows,
                        "row_count": len(
                            previous_rows
                        ),
                        "model": "local",
                        "visualization": (
                            previous_visualization
                        ),
                    }

        # ----------------------------------------------------
        # Grouped result / main insight
        # ----------------------------------------------------

        if len(previous_rows) > 1:

            first_row = previous_rows[0]

            if isinstance(first_row, dict):

                columns = list(
                    first_row.keys()
                )

                numeric_columns = []

                for column in columns:

                    values = [
                        row.get(column)
                        for row in previous_rows
                        if isinstance(row, dict)
                    ]

                    if any(
                        isinstance(value, (int, float))
                        and not isinstance(value, bool)
                        for value in values
                    ):
                        numeric_columns.append(column)

                if numeric_columns:

                    # Prefer business metrics such as revenue/sales/value.
                    preferred_metrics = [
                        column
                        for column in numeric_columns
                        if any(
                            keyword in column.lower()
                            for keyword in [
                                "revenue",
                                "sales",
                                "amount",
                                "value",
                                "units",
                                "total",
                            ]
                        )
                    ]

                    metric = (
                        preferred_metrics[-1]
                        if preferred_metrics
                        else numeric_columns[-1]
                    )

                    valid_rows = [
                        row
                        for row in previous_rows
                        if isinstance(row, dict)
                        and isinstance(row.get(metric), (int, float))
                        and not isinstance(row.get(metric), bool)
                    ]

                    if valid_rows:
                        highest = max(
                            valid_rows,
                            key=lambda row: float(row.get(metric)),
                        )

                        highest_value = float(highest.get(metric))

                        category_columns = [
                            column
                            for column in columns
                            if column != metric
                        ]

                        category_column = (
                            category_columns[0]
                            if category_columns
                            else None
                        )

                        category_value = (
                            highest.get(category_column)
                            if category_column
                            else None
                        )

                        total = sum(
                            float(row.get(metric))
                            for row in valid_rows
                        )

                        share_text = ""
                        if total:
                            share = (highest_value / total) * 100
                            share_text = (
                                f" It represents approximately "
                                f"{share:.1f}% of the returned total."
                            )

                        if category_column:
                            answer = (
                                f"The main insight is that "
                                f"{category_value} has the highest "
                                f"{metric.replace('_', ' ')} at "
                                f"{highest_value:,.0f}."
                                f"{share_text}"
                            )
                        else:
                            answer = (
                                f"The main insight is that the highest "
                                f"{metric.replace('_', ' ')} is "
                                f"{highest_value:,.0f}."
                                f"{share_text}"
                            )

                        return {
                            "question": question,
                            "type": "contextual_followup",
                            "answer": answer,
                            "sql": previous_assistant.get("sql"),
                            "columns": columns,
                            "rows": previous_rows,
                            "row_count": len(previous_rows),
                            "model": "local",
                            "visualization": previous_visualization,
                        }

        # ----------------------------------------------------
        # Fallback explanation using previous answer
        # ----------------------------------------------------

                        value = row.get(metric)

                        if isinstance(
                            value,
                            (int, float),
                        ) and not isinstance(
                            value,
                            bool,
                        ):
                            total += float(value)
                            numeric_count += 1

                    answer = (
                        f"The previous result contains "
                        f"{len(previous_rows)} groups. "
                        f"The '{metric.replace('_', ' ')}' "
                        f"values are being compared across "
                        f"those groups."
                    )

                    if numeric_count:
                        answer += (
                            f" Across the returned groups, "
                            f"their combined {metric.replace('_', ' ')} "
                            f"is approximately "
                            f"{total:,.2f}."
                        )

                    return {
                        "question": question,
                        "type": "contextual_followup",
                        "answer": answer,
                        "sql": previous_assistant.get(
                            "sql"
                        ),
                        "columns": columns,
                        "rows": previous_rows,
                        "row_count": len(
                            previous_rows
                        ),
                        "model": "local",
                        "visualization": (
                            previous_visualization
                        ),
                    }

        # ----------------------------------------------------
        # Fallback explanation using previous answer
        # ----------------------------------------------------

        answer = (
            "The previous answer was based on your "
            "dataset analysis. "
        )

        if previous_text:
            answer += (
                f"In particular, I previously found: "
                f"{previous_text}"
            )

        return {
            "question": question,
            "type": "contextual_followup",
            "answer": answer,
            "sql": previous_assistant.get("sql"),
            "columns": [],
            "rows": previous_rows,
            "row_count": len(previous_rows),
            "model": "local",
            "visualization": previous_visualization,
        }
    
def analyze_with_llm(
    dataset: Dataset,
    question: str,
    conversation_history: list[dict] | None = None,
) -> dict:
    """
    Main entry point used by FastAPI.

    Pipeline:

        User question
              ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬Å“
        Local Query Engine
              ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬Å“
        Local Forecast Analysis
              ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬Å“
        Local Trend Analysis
              ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬Å“
        Local Statistical Analysis
              ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬Å“
        Business Insight Analysis
              ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬Å“
        Local Grouped Analysis
              ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬Å“
        Local Numeric Analysis
              ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬Å“
        Gemini SQL Generation
              ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬Å“
        DuckDB
              ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬Å“
        Local answer formatting
              ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬Å“
        Visualization
    """

    total_start = time.time()

    print("\n==============================")
    print("AI ANALYST REQUEST")
    print("Question:", question)
    print("==============================")

    # --------------------------------------------------------
    # Validate question
    # --------------------------------------------------------

    if not isinstance(question, str):
        raise ValueError("Question must be a string.")

    question = question.strip()

    if not question:
        raise ValueError("Question cannot be empty.")

    conversation_history = _normalize_conversation_history(conversation_history)

    print(
        "Validation:",
        round(time.time() - total_start, 3),
        "seconds",
    )

    # --------------------------------------------------------
    # STEP 0
    # Handle conversational follow-ups BEFORE any expensive
    # analysis or Gemini fallback.
    # --------------------------------------------------------

    print("=== CONTEXTUAL FOLLOW-UP CODE ACTIVE ===")

    contextual_start = time.time()

    contextual_result = _try_contextual_followup(
        dataset,
        question,
        conversation_history,
    )

    print(
        "Contextual follow-up:",
        round(
            time.time() - contextual_start,
            3,
        ),
        "seconds",
    )

    if contextual_result is not None:

        print(
            "TOTAL:",
            round(
                time.time() - total_start,
                3,
            ),
            "seconds",
        )

        print(
            "RESULT: LOCAL CONTEXTUAL FOLLOW-UP"
        )

        print(
            "==============================\n"
        )

        return contextual_result

    # --------------------------------------------------------
    # STEP 1
    # Try simple local query engine
    # --------------------------------------------------------

    local_start = time.time()

    local_result = _try_local_query(
        dataset,
        question,
    )

    print(
        "Local query:",
        round(time.time() - local_start, 3),
        "seconds",
    )

    if local_result is not None:

        print(
            "TOTAL:",
            round(time.time() - total_start, 3),
            "seconds",
        )

        print("RESULT: LOCAL")
        print("==============================\n")

        return local_result

    # --------------------------------------------------------
    # STEP 2
    # Try local forecast analysis
    # --------------------------------------------------------

    forecast_start = time.time()

    forecast_result = _try_forecast_query(
        dataset,
        question,
    )

    print(
        "Forecast query:",
        round(time.time() - forecast_start, 3),
        "seconds",
    )

    if forecast_result is not None:
        print(
            "TOTAL:",
            round(time.time() - total_start, 3),
            "seconds",
        )
        print("RESULT: LOCAL FORECAST")
        print("==============================\\n")
        return forecast_result

    # --------------------------------------------------------
    # STEP 3
    # Try local trend analysis
    # --------------------------------------------------------

    trend_start = time.time()

    trend_result = _try_trend_query(
        dataset,
        question,
    )

    print(
        "Trend query:",
        round(time.time() - trend_start, 3),
        "seconds",
    )

    if trend_result is not None:
        print(
            "TOTAL:",
            round(time.time() - total_start, 3),
            "seconds",
        )
        print("RESULT: LOCAL TREND")
        print("==============================\\n")
        return trend_result

    # --------------------------------------------------------
    # STEP 4
    # Try local statistical analysis
    # --------------------------------------------------------

    statistical_start = time.time()

    statistical_result = _try_statistical_query(
        dataset,
        question,
    )

    print(
        "Statistical query:",
        round(time.time() - statistical_start, 3),
        "seconds",
    )

    if statistical_result is not None:
        print(
            "TOTAL:",
            round(time.time() - total_start, 3),
            "seconds",
        )
        print("RESULT: LOCAL STATISTICAL")
        print("==============================\\n")
        return statistical_result

    # --------------------------------------------------------
    # --------------------------------------------------------
    # STEP 5
    # Try dataset-level main insight analysis
    # --------------------------------------------------------

    main_insight_start = time.time()

    main_insight_result = _try_main_insight_query(
        dataset,
        question,
    )

    print(
        "Main insight:",
        round(
            time.time() - main_insight_start,
            3,
        ),
        "seconds",
    )

    if main_insight_result is not None:

        print(
            "TOTAL:",
            round(
                time.time() - total_start,
                3,
            ),
            "seconds",
        )

        print("RESULT: LOCAL MAIN INSIGHT")
        print("==============================\n")

        return main_insight_result

    # --------------------------------------------------------
    # STEP 6
    # Try business insight analysis
    # --------------------------------------------------------
    # STEP 5
    # Try business insight analysis
    # --------------------------------------------------------

    insight_start = time.time()

    insight_result = _try_business_insight_query(
        dataset,
        question,
    )

    print(
        "Business insight:",
        round(
            time.time() - insight_start,
            3,
        ),
        "seconds",
    )

    if insight_result is not None:

        print(
            "TOTAL:",
            round(
                time.time() - total_start,
                3,
            ),
            "seconds",
        )

        print("RESULT: LOCAL BUSINESS INSIGHT")
        print("==============================\n")

        return insight_result

    # --------------------------------------------------------
    # STEP 6
    # Try local grouped analysis
    # --------------------------------------------------------

    grouped_start = time.time()

    grouped_result = _try_grouped_query(
        dataset,
        question,
    )

    print(
        "Grouped query:",
        round(
            time.time() - grouped_start,
            3,
        ),
        "seconds",
    )

    if grouped_result is not None:

        print(
            "TOTAL:",
            round(
                time.time() - total_start,
                3,
            ),
            "seconds",
        )

        print("RESULT: LOCAL GROUPED")
        print("==============================\n")

        return grouped_result

    # --------------------------------------------------------
    # STEP 7
    # Try local numeric analysis
    # --------------------------------------------------------

    numeric_start = time.time()

    numeric_result = _try_numeric_query(
        dataset,
        question,
    )

    print(
        "Numeric query:",
        round(
            time.time() - numeric_start,
            3,
        ),
        "seconds",
    )

    if numeric_result is not None:

        print(
            "TOTAL:",
            round(
                time.time() - total_start,
                3,
            ),
            "seconds",
        )

        print("RESULT: LOCAL NUMERIC")
        print("==============================\n")

        return numeric_result

    # --------------------------------------------------------
    # STEP 8
    # Gemini generates SQL
    # --------------------------------------------------------

    print("Falling back to Gemini...")

    gemini_start = time.time()

    sql = _generate_sql(
        dataset,
        question,
        conversation_history,
    )

    print(
        "Gemini:",
        round(
            time.time() - gemini_start,
            3,
        ),
        "seconds",
    )

    # --------------------------------------------------------
    # STEP 9
    # Execute SQL
    # --------------------------------------------------------

    sql_start = time.time()

    columns, rows = _execute_sql(
        dataset,
        sql,
    )

    print(
        "DuckDB:",
        round(
            time.time() - sql_start,
            3,
        ),
        "seconds",
    )

    # --------------------------------------------------------
    # STEP 10
    # Format result locally
    # --------------------------------------------------------

    answer = _format_answer(
        question,
        columns,
        rows,
    )

    # --------------------------------------------------------
    # STEP 11
    # Select visualization
    # --------------------------------------------------------

    visualization = _choose_visualization(
        columns,
        rows,
    )

    # --------------------------------------------------------
    # STEP 12
    # Return response
    # --------------------------------------------------------

    total_time = round(
        time.time() - total_start,
        3,
    )

    print(
        "TOTAL:",
        total_time,
        "seconds",
    )

    print("RESULT: GEMINI")
    print("==============================\n")

    return {
        "question": question,
        "type": "llm_analysis",
        "answer": answer,
        "sql": sql,
        "columns": columns,
        "rows": _serialize_rows(
            columns,
            rows,
        ),
        "row_count": len(rows),
        "model": MODEL,
        "visualization": visualization,
    }


def _try_statistical_query(dataset, question: str) -> dict | None:
    """
    Handle common statistical analysis questions locally
    without using Gemini.
    """

    q = question.lower().strip()

    print("BUSINESS QUERY:", question)
    print("BUSINESS NORMALIZED:", q)

    # --------------------------------------------------------
    # Get schema
    # --------------------------------------------------------

    try:
        schema_rows = dataset.con.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'main_table'
            ORDER BY ordinal_position
            """
        ).fetchall()
    except Exception as exc:
        print(
            "Statistical schema lookup failed:",
            repr(exc),
        )
        return None

    schema = {
        str(row[0]).lower(): str(row[1]).upper()
        for row in schema_rows
    }

    numeric_columns = [
        column
        for column, data_type in schema.items()
        if any(
            dtype in data_type
            for dtype in [
                "INT",
                "DOUBLE",
                "FLOAT",
                "DECIMAL",
                "NUMERIC",
            ]
        )
    ]

    # --------------------------------------------------------
    # Find requested columns
    # --------------------------------------------------------

    selected_columns = []

    for column in numeric_columns:
        if column in q:
            selected_columns.append(column)

    # Business aliases
    aliases = {
        "sales": "revenue",
        "sale": "revenue",
        "income": "revenue",
        "earnings": "revenue",
        "marketing": "marketing_spend",
        "marketing spend": "marketing_spend",
        "marketing cost": "marketing_spend",
        "units": "units_sold",
        "price": "unit_price",
        "rating": "customer_rating",
        "returns": "returns",
    }

    for alias, column in aliases.items():
        if alias in q and column in schema:
            if column not in selected_columns:
                selected_columns.append(column)

    # --------------------------------------------------------
    # Correlation
    # --------------------------------------------------------

    # --------------------------------------------------------
    # Distribution / Histogram
    # --------------------------------------------------------

    if "distribution" in q:

        if not selected_columns:
            return None

        column = selected_columns[0]

        distribution_sql = f"""
        SELECT
            TRY_CAST("{column}" AS DOUBLE) AS "{column}"
        FROM main_table
        WHERE TRY_CAST("{column}" AS DOUBLE) IS NOT NULL
        ORDER BY "{column}"
        LIMIT 5000
        """.strip()

        try:
            distribution_result = dataset.con.execute(
                distribution_sql
            )

            distribution_columns = [
                description[0]
                for description in distribution_result.description
            ]

            distribution_rows = distribution_result.fetchall()

        except Exception as exc:
            print(
                "Distribution query failed:",
                repr(exc),
            )
            return None

        if not distribution_rows:
            return None

        return {
            "question": question,
            "type": "statistical_analysis",
            "answer": (
                f"Distribution of {column} "
                f"contains {len(distribution_rows)} numeric values."
            ),
            "sql": distribution_sql,
            "columns": distribution_columns,
            "rows": _serialize_rows(
                distribution_columns,
                distribution_rows,
            ),
            "chart_rows": _serialize_rows(
                distribution_columns,
                distribution_rows,
            ),
            "row_count": len(distribution_rows),
            "model": "local",
            "visualization": {
                "type": "histogram",
                "x": column,
                "title": f"Distribution of {column}",
            },
        }
    if "correlation" in q or "correlation between" in q:

        if len(selected_columns) < 2:
            return None

        col1 = selected_columns[0]
        col2 = selected_columns[1]

        correlation_sql = f"""
SELECT
    CORR(
        TRY_CAST("{col1}" AS DOUBLE),
        TRY_CAST("{col2}" AS DOUBLE)
    ) AS correlation
FROM main_table
""".strip()

        result = dataset.con.execute(
            correlation_sql
        ).fetchone()

        correlation = result[0] if result else None

        if correlation is None:
            return None

        # Fetch the actual paired observations so the frontend
        # scatter chart receives rows containing both x and y values.
        chart_sql = f"""
SELECT
    TRY_CAST("{col1}" AS DOUBLE) AS "{col1}",
    TRY_CAST("{col2}" AS DOUBLE) AS "{col2}"
FROM main_table
WHERE
    TRY_CAST("{col1}" AS DOUBLE) IS NOT NULL
    AND TRY_CAST("{col2}" AS DOUBLE) IS NOT NULL
LIMIT 1000
""".strip()

        chart_result = dataset.con.execute(
            chart_sql
        )

        chart_columns = [
            description[0]
            for description in chart_result.description
        ]

        chart_rows = chart_result.fetchall()

        return {
            "question": question,
            "type": "statistical_analysis",
            "answer": (
                f"The correlation between {col1} and "
                f"{col2} is {correlation:.4f}."
            ),
            "sql": correlation_sql,
            "columns": ["correlation"],
            "rows": [
                {
                    "correlation": correlation
                }
            ],
            "chart_rows": _serialize_rows(
                chart_columns,
                chart_rows,
            ),
            "row_count": 1,
            "model": "local",
            "visualization": {
                "type": "scatter",
                "x": col1,
                "y": col2,
                "title": f"{col1} vs {col2}",
            },
        }

    # --------------------------------------------------------
    # Median
    # --------------------------------------------------------

    if "median" in q:

        if not selected_columns:
            return None

        column = selected_columns[0]

        result = dataset.con.execute(
            f"""
            SELECT MEDIAN(
                TRY_CAST("{column}" AS DOUBLE)
            )
            FROM main_table
            """
        ).fetchone()

        value = result[0] if result else None

        if value is None:
            return None

        return {
            "question": question,
            "type": "statistical_analysis",
            "answer": (
                f"The median of {column} is {value:,.2f}."
            ),
            "sql": f"""
SELECT MEDIAN(
    TRY_CAST("{column}" AS DOUBLE)
)
FROM main_table
""".strip(),
            "columns": [column],
            "rows": [
                {
                    "median": float(value)
                }
            ],
            "row_count": 1,
            "model": "local",
            "visualization": {
                "type": "table",
            },
        }

    # --------------------------------------------------------
    # Standard deviation
    # --------------------------------------------------------

    if (
        "standard deviation" in q
        or "std deviation" in q
        or "std dev" in q
    ):

        if not selected_columns:
            return None

        column = selected_columns[0]

        result = dataset.con.execute(
            f"""
            SELECT STDDEV_SAMP(
                TRY_CAST("{column}" AS DOUBLE)
            )
            FROM main_table
            """
        ).fetchone()

        value = result[0] if result else None

        if value is None:
            return None

        return {
            "question": question,
            "type": "statistical_analysis",
            "answer": (
                f"The standard deviation of {column} "
                f"is {value:,.2f}."
            ),
            "sql": f"""
SELECT STDDEV_SAMP(
    TRY_CAST("{column}" AS DOUBLE)
)
FROM main_table
""".strip(),
            "columns": [column],
            "rows": [
                {
                    "standard_deviation": float(value)
                }
            ],
            "row_count": 1,
            "model": "local",
            "visualization": {
                "type": "table",
            },
        }

    # --------------------------------------------------------
    # Variance
    # --------------------------------------------------------

    if "variance" in q:

        if not selected_columns:
            return None

        column = selected_columns[0]

        result = dataset.con.execute(
            f"""
            SELECT VAR_SAMP(
                TRY_CAST("{column}" AS DOUBLE)
            )
            FROM main_table
            """
        ).fetchone()

        value = result[0] if result else None

        if value is None:
            return None

        return {
            "question": question,
            "type": "statistical_analysis",
            "answer": (
                f"The variance of {column} "
                f"is {value:,.2f}."
            ),
            "sql": f"""
SELECT VAR_SAMP(
    TRY_CAST("{column}" AS DOUBLE)
)
FROM main_table
""".strip(),
            "columns": [column],
            "rows": [
                {
                    "variance": float(value)
                }
            ],
            "row_count": 1,
            "model": "local",
            "visualization": {
                "type": "table",
            },
        }

    return None

def _try_forecast_query(dataset, question):
    """
    Handle simple time-series forecasting locally.

    Examples:
        Forecast revenue for the next 7 days
        Predict sales for the next 10 days
        Forecast revenue next 5 days
    """

    import re
    from datetime import timedelta

    q = question.lower().strip()

    print("BUSINESS QUERY:", question)
    print("BUSINESS NORMALIZED:", q)

    # ----------------------------------------------------------
    # Detect forecast question
    # ----------------------------------------------------------

    forecast_keywords = [
        "forecast",
        "predict",
        "prediction",
        "future revenue",
        "future sales",
        "next",
    ]

    if not any(
        keyword in q
        for keyword in forecast_keywords
    ):
        return None

    # ----------------------------------------------------------
    # Detect forecast horizon
    # ----------------------------------------------------------

    horizon = 7

    horizon_match = re.search(
        r"next\s+(\d+)\s*(day|days|week|weeks|month|months)",
        q,
    )

    if horizon_match:

        number = int(
            horizon_match.group(1)
        )

        unit = horizon_match.group(2)

        if "week" in unit:
            horizon = number * 7

        elif "month" in unit:
            horizon = number * 30

        else:
            horizon = number

    # Keep forecast reasonable
    horizon = max(
        1,
        min(horizon, 90)
    )

    # ----------------------------------------------------------
    # Get schema
    # ----------------------------------------------------------

    schema_rows = dataset.con.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'main_table'
        ORDER BY ordinal_position
        """
    ).fetchall()

    if not schema_rows:
        return None

    columns = [
        row[0]
        for row in schema_rows
    ]

    # ----------------------------------------------------------
    # Find date column
    # ----------------------------------------------------------

    date_column = None

    for column_name, data_type in schema_rows:

        data_type_upper = str(
            data_type
        ).upper()

        if (
            "DATE" in data_type_upper
            or "TIMESTAMP" in data_type_upper
            or "DATETIME" in data_type_upper
        ):
            date_column = column_name
            break

    # ----------------------------------------------------------
    # Fallback date column names
    # ----------------------------------------------------------

    if date_column is None:

        date_candidates = [
            "date",
            "datetime",
            "timestamp",
            "time",
            "day",
        ]

        for candidate in date_candidates:

            for column in columns:

                if column.lower() == candidate:
                    date_column = column
                    break

            if date_column:
                break

    if date_column is None:
        return None

    # ----------------------------------------------------------
    # Find metric column
    # ----------------------------------------------------------

    metric_column = None

    metric_aliases = {
        "revenue": [
            "revenue",
            "sales",
            "sale",
            "income",
            "earnings",
        ],
        "units_sold": [
            "units_sold",
            "units",
            "quantity",
            "qty",
        ],
        "unit_price": [
            "unit_price",
            "price",
        ],
        "marketing_spend": [
            "marketing_spend",
            "marketing",
            "marketing_cost",
        ],
    }

    for metric_name, aliases in metric_aliases.items():

        for column in columns:

            column_lower = column.lower()

            if column_lower in aliases:

                if (
                    metric_name in q
                    or any(
                        alias in q
                        for alias in aliases
                    )
                ):
                    metric_column = column
                    break

        if metric_column:
            break

    # ----------------------------------------------------------
    # Default to revenue
    # ----------------------------------------------------------

    if metric_column is None:

        for column in columns:

            if column.lower() == "revenue":
                metric_column = column
                break

    if metric_column is None:
        return None

    # ----------------------------------------------------------
    # Escape identifiers
    # ----------------------------------------------------------

    safe_date = date_column.replace(
        '"',
        '""'
    )

    safe_metric = metric_column.replace(
        '"',
        '""'
    )

    # ----------------------------------------------------------
    # Get historical data
    # ----------------------------------------------------------

    sql = f"""
        SELECT
            TRY_CAST(
                "{safe_date}" AS DATE
            ) AS "{safe_date}",

            SUM(
                TRY_CAST(
                    "{safe_metric}" AS DOUBLE
                )
            ) AS "{safe_metric}"

        FROM main_table

        WHERE TRY_CAST(
            "{safe_date}" AS DATE
        ) IS NOT NULL

        GROUP BY
            TRY_CAST(
                "{safe_date}" AS DATE
            )

        ORDER BY
            TRY_CAST(
                "{safe_date}" AS DATE
            )
    """

    try:

        result_rows = dataset.con.execute(
            sql
        ).fetchall()

    except Exception as error:

        print(
            "Forecast query error:",
            repr(error)
        )

        return None

    if len(result_rows) < 3:
        return None

    # ----------------------------------------------------------
    # Prepare historical data
    # ----------------------------------------------------------

    historical = []

    for date_value, metric_value in result_rows:

        if date_value is None:
            continue

        if metric_value is None:
            continue

        historical.append(
            {
                "date": date_value,
                "value": float(metric_value),
            }
        )

    if len(historical) < 3:
        return None

    # ----------------------------------------------------------
    # Linear regression
    #
    # y = slope*x + intercept
    # ----------------------------------------------------------

    x_values = list(
        range(len(historical))
    )

    y_values = [
        item["value"]
        for item in historical
    ]

    n = len(x_values)

    mean_x = sum(x_values) / n
    mean_y = sum(y_values) / n

    numerator = sum(
        (
            x - mean_x
        ) * (
            y - mean_y
        )
        for x, y in zip(
            x_values,
            y_values
        )
    )

    denominator = sum(
        (
            x - mean_x
        ) ** 2
        for x in x_values
    )

    if denominator == 0:
        return None

    slope = (
        numerator /
        denominator
    )

    intercept = (
        mean_y -
        slope * mean_x
    )

    # ----------------------------------------------------------
    # Build chart data
    # ----------------------------------------------------------

    rows = []

    for index, item in enumerate(
        historical
    ):

        date_value = item["date"]

        if hasattr(
            date_value,
            "isoformat"
        ):
            date_value = (
                date_value.isoformat()
            )

        rows.append(
            {
                "date": date_value,
                "revenue": item["value"],
                "forecast": None,
                "type": "historical",
            }
        )

    # ----------------------------------------------------------
    # Generate future forecast
    # ----------------------------------------------------------

    last_date = historical[-1]["date"]

    if not hasattr(
        last_date,
        "year"
    ):
        return None

    forecast_values = []

    for step in range(
        1,
        horizon + 1
    ):

        x = len(historical) + step - 1

        predicted_value = (
            slope * x +
            intercept
        )

        # Don't allow negative forecasts
        predicted_value = max(
            0,
            predicted_value
        )

        future_date = (
            last_date +
            timedelta(days=step)
        )

        rows.append(
            {
                "date": future_date.isoformat(),
                "revenue": None,
                "forecast": round(
                    predicted_value,
                    2
                ),
                "type": "forecast",
            }
        )

        forecast_values.append(
            predicted_value
        )

    # ----------------------------------------------------------
    # Determine forecast direction
    # ----------------------------------------------------------

    first_forecast = (
        forecast_values[0]
    )

    last_forecast = (
        forecast_values[-1]
    )

    if first_forecast == 0:

        forecast_change = 0

    else:

        forecast_change = (
            (
                last_forecast -
                first_forecast
            )
            / abs(first_forecast)
        ) * 100

    if forecast_change > 0:
        direction = "increase"

    elif forecast_change < 0:
        direction = "decrease"

    else:
        direction = "remain relatively stable"

    # ----------------------------------------------------------
    # Natural-language answer
    # ----------------------------------------------------------

    answer = (
        f"The forecast for the next "
        f"{horizon} days indicates that "
        f"{metric_column.replace('_', ' ')} "
        f"is expected to {direction}. "
        f"The forecast starts at approximately "
        f"{first_forecast:,.0f} and reaches "
        f"approximately "
        f"{last_forecast:,.0f}."
    )

    # ----------------------------------------------------------
    # Visualization
    # ----------------------------------------------------------

    visualization = {
        "type": "forecast",
        "x": "date",
        "y": "revenue",
        "forecastY": "forecast",
        "title": (
            f"{metric_column.replace('_', ' ').title()} "
            f"Forecast"
        ),
    }

    return {
        "question": question,
        "type": "forecast",
        "answer": answer,
        "sql": sql,
        "columns": [
            "date",
            "revenue",
            "forecast",
        ],
        "rows": rows,
        "row_count": len(rows),
        "model": "local",
        "visualization": visualization,
        "forecast_horizon": horizon,
    }

def _try_anomaly_query(dataset, question):
    """
    Detect unusual/outlier values in a numeric column using z-score.

    A z-score >= 2 is used as a screening threshold.
    This identifies potentially unusual values; it does not prove
    that the data point is an error or fraud.
    """

    if dataset is None or getattr(dataset, "con", None) is None:
        return None

    con = dataset.con

    try:
        # --------------------------------------------------------
        # Get numeric columns
        # --------------------------------------------------------

        columns_result = con.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'main_table'
            """
        ).fetchall()

        numeric_types = {
            "INTEGER",
            "BIGINT",
            "DOUBLE",
            "FLOAT",
            "DECIMAL",
            "HUGEINT",
            "SMALLINT",
            "TINYINT",
            "REAL",
        }

        numeric_columns = []

        for column_name, data_type in columns_result:
            data_type_upper = str(data_type).upper()

            if any(
                numeric_type in data_type_upper
                for numeric_type in numeric_types
            ):
                numeric_columns.append(column_name)

        if not numeric_columns:
            return None

        # --------------------------------------------------------
        # Detect which column the user is asking about
        # --------------------------------------------------------

        q = question.lower()

        aliases = {
            "sales": "revenue",
            "sale": "revenue",
            "income": "revenue",
            "earnings": "revenue",
            "units": "units_sold",
            "price": "unit_price",
            "marketing": "marketing_spend",
            "rating": "customer_rating",
            "returns": "returns",
        }

        selected_column = None

        # First look for an exact column name
        for column in numeric_columns:
            if column.lower() in q:
                selected_column = column
                break

        # Then check aliases
        if selected_column is None:
            for keyword, column in aliases.items():
                if keyword in q and column in numeric_columns:
                    selected_column = column
                    break

        # Default to revenue if available
        if selected_column is None:
            if "revenue" in numeric_columns:
                selected_column = "revenue"
            else:
                selected_column = numeric_columns[0]

        # --------------------------------------------------------
        # Run anomaly detection
        # --------------------------------------------------------

        query = f"""
        WITH scored AS (
            SELECT
                ROW_NUMBER() OVER () AS row_number,
                TRY_CAST("{selected_column}" AS DOUBLE) AS value,
                AVG(
                    TRY_CAST("{selected_column}" AS DOUBLE)
                ) OVER () AS mean_value,
                STDDEV_SAMP(
                    TRY_CAST("{selected_column}" AS DOUBLE)
                ) OVER () AS stddev_value
            FROM main_table
            WHERE TRY_CAST(
                "{selected_column}" AS DOUBLE
            ) IS NOT NULL
        ),

        anomaly_scores AS (
            SELECT
                row_number,
                value,
                mean_value,
                stddev_value,
                ABS(
                    (value - mean_value)
                    / NULLIF(stddev_value, 0)
                ) AS z_score
            FROM scored
        )

        SELECT
            row_number,
            value,
            mean_value,
            stddev_value,
            z_score
        FROM anomaly_scores
        WHERE z_score >= 2
        ORDER BY z_score DESC
        LIMIT 10
        """

        result = con.execute(query)
        rows_data = result.fetchall()

        columns = [
            description[0]
            for description in result.description
        ]

        # --------------------------------------------------------
        # No anomalies
        # --------------------------------------------------------

        if not rows_data:
            return {
                "status": "success",
                "type": "anomaly_detection",
                "answer": (
                    f"No unusual {selected_column} values were "
                    "detected using the z-score screening threshold "
                    "of 2."
                ),
                "sql": query,
                "columns": columns,
                "rows": [],
                "row_count": 0,
                "model": "local",
                "visualization": None,
            }

        # --------------------------------------------------------
        # Convert rows to dictionaries
        # --------------------------------------------------------

        rows = [
            dict(zip(columns, row))
            for row in rows_data
        ]

        anomaly_count = len(rows)

        # Highest anomaly
        highest_anomaly = rows[0]

        answer = (
            f"Found {anomaly_count} potentially unusual "
            f"{selected_column} value(s) using a z-score "
            f"threshold of 2. "
            f"The most unusual value is "
            f"{highest_anomaly['value']:,.2f} "
            f"with a z-score of "
            f"{highest_anomaly['z_score']:.2f}. "
            f"These are statistical outliers and should be "
            f"investigated further rather than automatically "
            f"treated as errors."
        )

        return {
            "status": "success",
            "type": "anomaly_detection",
            "answer": answer,
            "sql": query,
            
            "columns": columns,
            "rows": rows,
            "row_count": anomaly_count,
            "model": "local",
            "visualization": {
                "type": "bar",
                "x": "row_number",
                "y": "value",
                "title": (
                    f"Potential anomalies in "
                    f"{selected_column}"
                ),
            },
        }

    except Exception as e:
        print(
            "Anomaly detection error:",
            repr(e)
        )

        return None




























