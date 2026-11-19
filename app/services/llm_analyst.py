import os
import re
import time
import math
from typing import Any

from dotenv import load_dotenv

from app.services.data_loader import Dataset

try:
    from google import genai
except Exception:
    genai = None


# ============================================================================
# GENERIC AI DATA ANALYST ENGINE
# ============================================================================
#
# Design:
#   question
#      -> schema understanding
#      -> intent/column resolution
#      -> deterministic DuckDB analysis
#      -> result formatting + visualization
#      -> Gemini SQL fallback when the local planner cannot resolve a query
#
# This file intentionally avoids business-specific metric assumptions.
# It is designed to work from the uploaded dataset's actual schema.
# ============================================================================

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = "gemini-3.6-flash"

_client = None
if GEMINI_API_KEY and genai is not None:
    try:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception:
        _client = None


# ============================================================================
# Core helpers
# ============================================================================

def _q(column: str) -> str:
    """Safely quote a DuckDB identifier."""
    return '"' + str(column).replace('"', '""') + '"'


def _norm(value: Any) -> str:
    """Normalize natural-language text and column names for matching."""
    value = str(value or "").strip().lower()
    value = re.sub(r"[_\-]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value


def _readable(column: str) -> str:
    return re.sub(r"\s+", " ", str(column).replace("_", " ")).strip()


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _schema(dataset: Dataset) -> list[dict[str, str]]:
    """Read the real DuckDB schema; no hard-coded dataset columns."""
    rows = dataset.con.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'main_table'
        ORDER BY ordinal_position
        """
    ).fetchall()

    return [
        {"name": str(row[0]), "type": str(row[1])}
        for row in rows
    ]


def _columns(dataset: Dataset) -> list[str]:
    return [item["name"] for item in _schema(dataset)]


def _numeric_columns(dataset: Dataset) -> list[str]:
    numeric_types = (
        "INTEGER",
        "BIGINT",
        "SMALLINT",
        "TINYINT",
        "HUGEINT",
        "DECIMAL",
        "DOUBLE",
        "FLOAT",
        "REAL",
        "UBIGINT",
        "UINTEGER",
        "USMALLINT",
        "UTINYINT",
    )

    return [
        item["name"]
        for item in _schema(dataset)
        if any(
            numeric_type in item["type"].upper()
            for numeric_type in numeric_types
        )
    ]


def _date_columns(dataset: Dataset) -> list[str]:
    return [
        item["name"]
        for item in _schema(dataset)
        if any(
            data_type in item["type"].upper()
            for data_type in ("DATE", "TIMESTAMP", "TIME")
        )
    ]


def _rows_to_dicts(description, rows) -> list[dict[str, Any]]:
    names = [str(item[0]) for item in description]
    return [
        dict(zip(names, row))
        for row in rows
    ]


def _execute(
    dataset: Dataset,
    sql: str,
) -> tuple[list[str], list[dict[str, Any]]]:
    cursor = dataset.con.execute(sql)
    rows = cursor.fetchall()

    return (
        [str(item[0]) for item in cursor.description],
        _rows_to_dicts(cursor.description, rows),
    )


def _base_result(
    question: str,
    result_type: str,
    answer: str,
    sql: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    visualization: dict | None = None,
    **extra,
) -> dict:
    result = {
        "question": question,
        "type": result_type,
        "answer": answer,
        "sql": sql.strip() if sql else None,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "model": "local",
        "visualization": visualization or {
            "type": "table",
            "x": "",
            "y": "",
            "title": "",
        },
    }

    result.update(extra)
    return result


def _clean_sql(text: str) -> str:
    """Clean a Gemini SQL response."""
    text = str(text or "").strip()

    text = re.sub(
        r"^\s*```(?:sql)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\s*```\s*$",
        "",
        text,
    )

    match = re.search(
        r"\b(?:SELECT|WITH)\b",
        text,
        flags=re.IGNORECASE,
    )

    if match:
        text = text[match.start():]

    return text.rstrip(";").strip()


def _is_read_only_sql(sql: str) -> bool:
    """Reject unsafe SQL before execution."""
    cleaned = _clean_sql(sql).lower()

    if not (
        cleaned.startswith("select")
        or cleaned.startswith("with")
    ):
        return False

    forbidden = (
        r"\b(insert|update|delete|drop|alter|create|truncate|"
        r"copy|attach|detach|install|load|pragma)\b"
    )

    return re.search(forbidden, cleaned) is None


# ============================================================================
# Generic question understanding
# ============================================================================

_AGG_WORDS = {
    "average": "AVG",
    "avg": "AVG",
    "mean": "AVG",
    "sum": "SUM",
    "total": "SUM",
    "minimum": "MIN",
    "lowest": "MIN",
    "smallest": "MIN",
    "maximum": "MAX",
    "highest": "MAX",
    "largest": "MAX",
    "median": "MEDIAN",
    "count": "COUNT",
    "number": "COUNT",
    "how many": "COUNT",
}


def _find_mentioned_columns(
    question: str,
    columns: list[str],
) -> list[str]:
    """
    Resolve all dataset columns explicitly mentioned in a question.

    Important:
    The returned columns preserve the order in which the columns
    appear in the user's question rather than the order of the
    dataset schema.

    Examples:
        "average Mathematics, Programming, and Data_Science"
            -> ["Mathematics", "Programming", "Data_Science"]

        "compare Revenue and Profit"
            -> ["Revenue", "Profit"]

    Matching is dataset-independent and supports:
        - underscores vs spaces
        - case differences
        - multi-word column names
        - arbitrary column names
    """

    q = _norm(question)

    if not q or not columns:
        return []

    matches = []

    # Longer column names are matched first so that overlapping
    # names do not incorrectly capture a shorter column.
    candidates = sorted(
        columns,
        key=lambda value: len(_norm(value)),
        reverse=True,
    )

    for column in candidates:
        normalized_column = _norm(column)

        if not normalized_column:
            continue

        match = re.search(
            r"(?<!\w)"
            + re.escape(normalized_column)
            + r"(?!\w)",
            q,
            re.IGNORECASE,
        )

        if not match:
            continue

        matches.append(
            (
                match.start(),
                match.end(),
                column,
            )
        )

    if not matches:
        return []

    # Sort by where the column appears in the user's question.
    matches.sort(key=lambda item: (item[0], -(item[1] - item[0])))

    # Prevent overlapping matches.
    # Example:
    #   "Data Science"
    # should not also produce a shorter overlapping match.
    selected = []
    occupied = []

    for start_pos, end_pos, column in matches:
        overlaps = any(
            start_pos < existing_end
            and end_pos > existing_start
            for existing_start, existing_end in occupied
        )

        if overlaps:
            continue

        if column in selected:
            continue

        selected.append(column)
        occupied.append((start_pos, end_pos))

    return selected

def _resolve_column(
    text: str,
    columns: list[str],
    numeric_only: bool = False,
    numeric: list[str] | None = None,
) -> str | None:
    q = _norm(text)

    candidates = (
        numeric
        if numeric_only and numeric is not None
        else columns
    )

    normalized = {
        _norm(column): column
        for column in candidates
    }

    if q in normalized:
        return normalized[q]

    # Domain synonym: in datasets where a separate Region field is absent,
    # a Team field containing geographic labels (North/South/East/West) can
    # represent the region dimension. Exact real columns always take priority.
    geographic_aliases = {
        "region": {"region", "regions", "territory", "territories", "area", "areas"},
        "regions": {"region", "regions", "territory", "territories", "area", "areas"},
        "territory": {"region", "regions", "territory", "territories", "area", "areas"},
        "territories": {"region", "regions", "territory", "territories", "area", "areas"},
    }
    if q in geographic_aliases and "team" in normalized:
        return normalized["team"]

    for name in sorted(
        normalized,
        key=len,
        reverse=True,
    ):
        if re.search(
            r"(?<!\w)"
            + re.escape(name)
            + r"(?!\w)",
            q,
        ):
            return normalized[name]

    q_tokens = set(q.split())

    best = None
    best_score = 0.0

    for name, original in normalized.items():
        name_tokens = set(name.split())

        if not name_tokens:
            continue

        score = (
            len(q_tokens & name_tokens)
            / len(name_tokens)
        )

        if score > best_score and score >= 0.5:
            best_score = score
            best = original

    return best


def _detect_aggregation(question: str) -> str | None:
    q = _norm(question)

    for phrase in sorted(
        _AGG_WORDS,
        key=len,
        reverse=True,
    ):
        if re.search(
            r"(?<!\w)"
            + re.escape(phrase)
            + r"(?!\w)",
            q,
        ):
            return _AGG_WORDS[phrase]

    return None


def _detect_group_column(
    question: str,
    columns: list[str],
) -> str | None:
    """
    Resolve an explicit or implicit grouping dimension.

    Explicit grouping examples:
      - average CGPA by Department
      - count for each Department
      - average score per Class
      - sales across Region

    Implicit ranking examples:
      - Which Department has the highest average CGPA?
      - Which Region has the lowest average Profit?
      - What Category has the highest average Score?

    Simple metric questions such as:
      - What is the average Percentage?
      - What is the maximum Percentage?
      - What is the minimum Percentage?
      - What is the total of Total_Marks?

    must NOT treat the metric column itself as a grouping column.
    """
    q = _norm(question)

    # ------------------------------------------------------------
    # Explicit SORT / ORDER grouping
    # ------------------------------------------------------------
    #
    # Examples:
    #   Sort Departments by average Percentage
    #   Sort Departments by average Percentage descending
    #   Order Departments by total Sales
    #
    # Structure:
    #   SORT <GROUP> BY <AGGREGATION> <METRIC>
    #
    # This must be handled before the generic "by ..." parser.
    # ------------------------------------------------------------
    sort_match = re.search(
        r"\b(?:sort|order|rank)\s+(.+?)\s+by\s+"
        r"(?:average|avg|mean|sum|total|maximum|max|minimum|min|median)\s+"
        r"(.+?)(?:\s+(?:in\s+)?(?:ascending|descending|asc|desc)\b|[?.!,]|$)",
        q,
        re.IGNORECASE,
    )

    if sort_match:
        group_text = sort_match.group(1).strip()

        # Exact resolution.
        resolved = _resolve_column(
            group_text,
            columns,
        )

        if resolved:
            return resolved

        # Generic plural -> singular.
        if group_text.lower().endswith("s"):
            singular = group_text[:-1].strip()

            resolved = _resolve_column(
                singular,
                columns,
            )

            if resolved:
                return resolved

        # Common English pluralization:
        # categories -> category
        # companies -> company
        if group_text.lower().endswith("ies"):
            singular = group_text[:-3] + "y"

            resolved = _resolve_column(
                singular,
                columns,
            )

            if resolved:
                return resolved

        # Try progressively shorter candidates.
        words = group_text.split()

        for end in range(len(words) - 1, 0, -1):
            candidate = " ".join(words[:end]).strip()

            resolved = _resolve_column(
                candidate,
                columns,
            )

            if resolved:
                return resolved

            if candidate.lower().endswith("s"):
                singular = candidate[:-1].strip()

                resolved = _resolve_column(
                    singular,
                    columns,
                )

                if resolved:
                    return resolved

            if candidate.lower().endswith("ies"):
                singular = candidate[:-3] + "y"

                resolved = _resolve_column(
                    singular,
                    columns,
                )

                if resolved:
                    return resolved


    # ------------------------------------------------------------
    # 0. Explicit TOP/BOTTOM N ranking dimension
    # ------------------------------------------------------------
    #
    # This MUST run before the generic "by ..." grouping detector.
    #
    # Example:
    #   top 3 Departments by average Percentage
    #
    # The generic "by" pattern would otherwise interpret
    # "average Percentage" as the grouping column.
    # ------------------------------------------------------------
    top_bottom_match = re.search(
        r"\b(?:top|bottom)\s+\d+\s+(.+?)\s+by\b",
        q,
        re.IGNORECASE,
    )

    if top_bottom_match:
        candidate_text = top_bottom_match.group(1).strip()

        # Exact resolution first.
        resolved = _resolve_column(
            candidate_text,
            columns,
        )

        if resolved:
            return resolved

        # Generic plural -> singular resolution.
        if candidate_text.lower().endswith("s"):
            singular = candidate_text[:-1].strip()

            resolved = _resolve_column(
                singular,
                columns,
            )

            if resolved:
                return resolved

        # Try progressively shorter candidates.
        words = candidate_text.split()

        for end in range(len(words) - 1, 0, -1):
            candidate = " ".join(words[:end]).strip()

            resolved = _resolve_column(
                candidate,
                columns,
            )

            if resolved:
                return resolved

            if candidate.lower().endswith("s"):
                singular = candidate[:-1].strip()

                resolved = _resolve_column(
                    singular,
                    columns,
                )

                if resolved:
                    return resolved

    # ------------------------------------------------------------
    # 1. Explicit grouping phrases
    # ------------------------------------------------------------
    patterns = [
        r"\bby\s+(.+?)(?:\s+(?:with|where|having|for|from|that|who|and)\b|[?.!,]|$)",
        r"\bfor each\s+(.+?)(?:\s+(?:with|where|having|for|from|that|who|and)\b|[?.!,]|$)",
        r"\beach\s+(.+?)(?:\s+(?:with|where|having|for|from|that|who|and)\b|[?.!,]|$)",
        r"\bper\s+(.+?)(?:\s+(?:with|where|having|for|from|that|who|and)\b|[?.!,]|$)",
        r"\bacross\s+(.+?)(?:\s+(?:with|where|having|for|from|that|who|and)\b|[?.!,]|$)",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            q,
            flags=re.IGNORECASE,
        )

        if match:
            candidate = match.group(1).strip()
            column = _resolve_column(
                candidate,
                columns,
            )

            if column:
                return column

            # Natural-language dimensions are commonly pluralized:
            # "across regions" -> the real "region" column.
            simple_singular = candidate[:-1].strip() if candidate.endswith("s") else candidate
            if simple_singular and simple_singular != candidate:
                column = _resolve_column(simple_singular, columns)
                if column:
                    return column
            if candidate.endswith("ies"):
                column = _resolve_column(candidate[:-3] + "y", columns)
                if column:
                    return column

    # ------------------------------------------------------------
    # 2. Implicit grouping for ranking/comparison questions
    # ------------------------------------------------------------
    #
    # IMPORTANT:
    # "What is the average Percentage?"
    # must NOT become GROUP = Percentage.
    #
    # But:
    # "Which Department has the highest average Percentage?"
    # should become GROUP = Department.
    #
    # Therefore "what" or "which" alone is insufficient. We require
    # actual ranking/comparison language as well.
    # ------------------------------------------------------------
    ranking_words = (
        "highest",
        "lowest",
        "largest",
        "smallest",
        "top",
        "bottom",
        "leading",
        "best",
        "worst",
        "most",
        "least",
        "ranked",
        "ranking",
        "rank",
    )

    has_ranking_language = any(
        word in q
        for word in ranking_words
    )

    if has_ranking_language:

        # --------------------------------------------------------
        # Explicit TOP/BOTTOM N dimension
        # --------------------------------------------------------
        #
        # Examples:
        #   top 3 Departments by average Percentage
        #   bottom 3 Departments by average Percentage
        #   top 5 Regions by total Revenue
        #   bottom 10 Products by average Rating
        #
        # Resolve the grouping dimension directly from the text
        # instead of relying on mention ordering.
        # --------------------------------------------------------
        top_bottom_match = re.search(
            r"\b(?:top|bottom)\s+\d+\s+(.+?)\s+by\b",
            q,
            re.IGNORECASE,
        )

        if top_bottom_match:
            candidate_text = top_bottom_match.group(1).strip()

            # First try the complete candidate.
            resolved = _resolve_column(
                candidate_text,
                columns,
            )

            if resolved:
                return resolved

            # Then progressively shorten the candidate.
            # This handles phrases such as:
            #   "student departments"
            #   "sales regions"
            candidate_words = candidate_text.split()

            for end in range(len(candidate_words), 0, -1):
                candidate = " ".join(candidate_words[:end]).strip()

                resolved = _resolve_column(
                    candidate,
                    columns,
                )

                if resolved:
                    return resolved

                # Handle simple plural forms.
                if candidate.lower().endswith("s"):
                    singular = candidate[:-1].strip()

                    resolved = _resolve_column(
                        singular,
                        columns,
                    )

                    if resolved:
                        return resolved

        mentioned = _find_mentioned_columns(
            q,
            columns,
        )

        if mentioned:
            # Prefer a non-numeric/dimension column as the grouping
            # column when the question contains both a dimension and
            # a numeric metric.
            # In ranking questions, the grouping dimension is normally
            # the column associated with "which/what/top/bottom", while
            # the numeric metric is associated with average/sum/etc.
            # Prefer the first column that appears before the metric
            # when the question explicitly names a dimension.
            for column in mentioned:
                readable = str(column).lower().replace("_", " ")
                ranking_patterns = (
                    rf"\bwhich\s+(?:the\s+)?{re.escape(readable)}\b",
                    rf"\bwhat\s+(?:the\s+)?{re.escape(readable)}\b",
                    rf"\btop(?:\s+\d+)?\s+{re.escape(readable)}s?\b",
                    rf"\bbottom(?:\s+\d+)?\s+{re.escape(readable)}s?\b",
                    rf"\bhighest\s+{re.escape(readable)}s?\b",
                    rf"\blowest\s+{re.escape(readable)}s?\b",
                )

                if any(
                    re.search(pattern, q, re.IGNORECASE)
                    for pattern in ranking_patterns
                ):
                    return column

            # Generic TOP/BOTTOM ranking:
            # resolve the dimension that appears after the ranking
            # keyword, optionally after an integer.
            #
            # Examples:
            #   top 3 Departments by average Percentage
            #   bottom 5 Regions by total Revenue
            #   top Categories by average Score
            ranking_dimension_pattern = re.compile(
                r"\b(?:top|bottom)\s+(?:\d+\s+)?(.+?)(?:\s+by\s+|\s+with\s+|\s+where\s+|$)",
                re.IGNORECASE,
            )

            ranking_match = ranking_dimension_pattern.search(q)

            if ranking_match:
                candidate_text = ranking_match.group(1).strip()

                # Try the complete candidate first.
                resolved = _resolve_column(
                    candidate_text,
                    columns,
                )

                if resolved:
                    return resolved

                # Candidate may contain a pluralized column name.
                candidate_words = candidate_text.split()

                for end in range(len(candidate_words), 0, -1):
                    candidate = " ".join(candidate_words[:end]).strip()

                    resolved = _resolve_column(
                        candidate,
                        columns,
                    )

                    if resolved:
                        return resolved

                    # Remove a trailing plural 's'.
                    singular = candidate[:-1] if candidate.endswith("s") else candidate

                    resolved = _resolve_column(
                        singular,
                        columns,
                    )

                    if resolved:
                        return resolved

            # Generic ranking fallback:
            # prefer non-numeric columns over numeric metric columns.
            non_numeric = [
                column
                for column in mentioned
                if column not in numeric
            ]

            if non_numeric:
                return non_numeric[0]

            return mentioned[0]

    return None

def _detect_metric_column(
    question: str,
    columns: list[str],
    numeric: list[str],
    exclude: str | None = None,
) -> str | None:
    q = _norm(question)
    mentioned = _find_mentioned_columns(question, columns)

    # An explicit dataset column name always wins over a synonym.
    for column in mentioned:
        if column != exclude and column in numeric:
            return column

    # Resolve common business language to a real numeric field only
    # when the dataset contains exactly one unambiguous candidate.
    semantic_aliases = {
        "revenue": {"revenue", "sales", "turnover", "income", "gross sales"},
        "cost": {"cost", "spend", "expense", "expenses", "marketing spend", "marketing cost", "budget"},
        "leads": {"lead", "leads"},
        "conversions": {"conversion", "conversions", "orders", "closed deals"},
        "quantity": {"quantity", "units", "units sold"},
    }

    for aliases in semantic_aliases.values():
        if not any(
            re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", q)
            for alias in aliases
        ):
            continue

        candidates = [
            column
            for column in numeric
            if _norm(column) in aliases
        ]
        if len(candidates) == 1:
            return candidates[0]

    # Safe fallback only when there is exactly one numeric column.
    if len(numeric) == 1 and any(
        re.search(
            r"(?<!\w)" + re.escape(marker) + r"(?!\w)",
            q,
        )
        for marker in (
            "average", "avg", "mean", "sum", "total",
            "highest", "lowest", "maximum", "minimum",
            "median", "top", "bottom",
        )
    ):
        return numeric[0]

    return None

def _try_comparison_query(
    dataset: Dataset,
    question: str,
) -> dict | None:
    """
    Dedicated comparison entry point.

    The comparison implementation currently lives inside
    _try_local_query(). This wrapper exposes all valid
    comparison_analysis results to AnalystAgent.
    """

    result = _try_local_query(
        dataset,
        question,
    )

    if not result:
        return None

    # _try_local_query() uses the canonical comparison
    # result type "comparison_analysis".
    if result.get("type") == "comparison_analysis":
        return result

    return None

# Local analysis engines
# ============================================================================

def _try_local_query(
    dataset: Dataset,
    question: str,
) -> dict | None:
    """
    Handle simple dataset-independent questions:
      - total row count
      - column listing
      - AVG/SUM/MIN/MAX/MEDIAN/COUNT
      - correlation between two numeric columns
    """
    q = _norm(question)
    columns = _columns(dataset)
    numeric = _numeric_columns(dataset)

    if not columns:
        return None

    # ------------------------------------------------------------
    # Total number of records
    # ------------------------------------------------------------
    if re.search(
        r"\b(how many|number of|count)\b.*"
        r"\b(students|records|rows|observations|entries|"
        r"people|items|samples|data|users|customers)\b",
        q,
    ):
        sql = """
            SELECT COUNT(*) AS count
            FROM main_table
        """

        result_columns, rows = _execute(
            dataset,
            sql,
        )

        count = (
            int(rows[0]["count"])
            if rows and rows[0]["count"] is not None
            else 0
        )

        return _base_result(
            question,
            "local_query",
            f"There are {count:,} records in the dataset.",
            sql,
            result_columns,
            rows,
            {
                "type": "metric",
                "x": "",
                "y": "count",
                "title": "Record Count",
            },
        )

    # ------------------------------------------------------------
    # Column listing
    # ------------------------------------------------------------
    if any(
        phrase in q
        for phrase in (
            "how many columns",
            "number of columns",
            "what columns",
            "list the columns",
            "column names",
        )
    ):
        sql = """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'main_table'
            ORDER BY ordinal_position
        """

        result_columns, rows = _execute(
            dataset,
            sql,
        )

        answer = (
            f"The dataset has {len(rows)} columns: "
            + ", ".join(
                str(row["column_name"])
                for row in rows
            )
            + "."
        )

        return _base_result(
            question,
            "dataset_overview",
            answer,
            sql,
            result_columns,
            rows,
        )

    # ------------------------------------------------------------
    # Generic multi-column comparison
    # ------------------------------------------------------------
    # Handles questions such as:
    #   Compare Mathematics and Programming
    #   Which has the higher average, Mathematics or Programming?
    #   What is the difference between the average of Revenue and Profit?
    #
    # This is completely dataset-agnostic. The mentioned numeric
    # columns are resolved dynamically from the dataset schema.
    # ------------------------------------------------------------

    comparison_language = any(
        phrase in q
        for phrase in (
            "compare",
            "comparison",
            "difference between",
            "difference of",
            "higher",
            "lower",
            "greater",
            "less",
            "which has",
            "which is higher",
            "which is lower",
            "ratio",
            "percentage higher",
            "percentage lower",
            "percentage difference",
            "percent higher",
            "percent lower",
            "percent difference",
            "how many times",
            "times as much",
            "times higher",
        )
    )

    if comparison_language:
        # Remove comparison-language phrases before resolving columns.
        # This prevents words such as "percentage" in
        # "percentage higher" from being mistaken for an actual
        # dataset column named "Percentage".
        comparison_column_text = q

        comparison_phrases = (
            "percentage higher",
            "percentage lower",
            "percentage difference",
            "percent higher",
            "percent lower",
            "percent difference",
            "% higher",
            "% lower",
            "how many times",
            "times as much",
            "times higher",
            "difference between",
            "difference of",
        )

        for phrase in comparison_phrases:
            comparison_column_text = comparison_column_text.replace(
                phrase,
                " ",
            )

        mentioned_numeric = [
            column
            for column in _find_mentioned_columns(
                comparison_column_text,
                columns,
            )
            if column in numeric
        ]

        # Comparison requires at least two explicitly mentioned
        # numeric columns.
        if len(mentioned_numeric) >= 2:

            # Resolve the requested aggregation.
            comparison_aggregation = _detect_aggregation(q)

            # "Compare X and Y" has no explicit aggregation, so
            # average is the natural statistical comparison.
            if comparison_aggregation in (None, "COUNT"):
                comparison_aggregation = "AVG"

            # Only use supported numeric aggregations.
            if comparison_aggregation not in (
                "AVG",
                "SUM",
                "MIN",
                "MAX",
                "MEDIAN",
            ):
                comparison_aggregation = "AVG"

            aliases = []
            expressions = []

            for metric_column in mentioned_numeric:
                readable_metric = _readable(metric_column)

                safe_name = re.sub(
                    r"[^a-zA-Z0-9]+",
                    "_",
                    readable_metric,
                ).strip("_").lower()

                alias = (
                    f"{comparison_aggregation.lower()}_{safe_name}"
                )

                base_alias = alias
                suffix = 2

                while alias in aliases:
                    alias = f"{base_alias}_{suffix}"
                    suffix += 1

                aliases.append(alias)

                expressions.append(
                    f"{comparison_aggregation}("
                    f"TRY_CAST({_q(metric_column)} AS DOUBLE)"
                    f") AS {_q(alias)}"
                )

            sql = (
                "SELECT "
                + ", ".join(expressions)
                + " FROM main_table"
            )

            result_columns, rows = _execute(
                dataset,
                sql,
            )

            if rows:
                row = rows[0]

                values = []

                for metric_column, alias in zip(
                    mentioned_numeric,
                    aliases,
                ):
                    value = row.get(alias)

                    if value is None:
                        continue

                    try:
                        value_float = float(value)
                    except (TypeError, ValueError):
                        continue

                    values.append(
                        (
                            metric_column,
                            value_float,
                        )
                    )

                if len(values) >= 2:

                    label = {
                        "AVG": "average",
                        "SUM": "sum",
                        "MIN": "minimum",
                        "MAX": "maximum",
                        "MEDIAN": "median",
                    }.get(
                        comparison_aggregation,
                        comparison_aggregation.lower(),
                    )

                    # ------------------------------------------------
                    # Derived comparison analysis
                    # ------------------------------------------------
                    #
                    # Derived comparisons use the semantic order expressed
                    # in the question rather than relying only on the
                    # column-resolution order.
                    #
                    # Examples:
                    #   Programming to Mathematics
                    #       -> Programming / Mathematics
                    #
                    #   Programming percentage higher than Mathematics
                    #       -> (Programming - Mathematics) / Mathematics
                    #
                    #   Mathematics percentage lower than Programming
                    #       -> (Programming - Mathematics) / Programming
                    # ------------------------------------------------

                    answer = None

                    if len(values) == 2:
                        value_map = {
                            name: value
                            for name, value in values
                        }

                        semantic_values = values

                        # Try to preserve the explicit "X to Y",
                        # "X than Y", or "X compared with Y" ordering.
                        #
                        # We use the positions of the resolved column names
                        # inside the normalized question so that the order
                        # follows the user's wording.
                        ordered_mentions = []

                        for name, value in values:
                            normalized_name = _norm(name)

                            match = re.search(
                                r"(?<!\w)"
                                + re.escape(normalized_name)
                                + r"(?!\w)",
                                q,
                                re.IGNORECASE,
                            )

                            if match:
                                ordered_mentions.append(
                                    (
                                        match.start(),
                                        name,
                                        value,
                                    )
                                )

                        if len(ordered_mentions) >= 2:
                            ordered_mentions.sort(
                                key=lambda item: item[0]
                            )

                            semantic_values = [
                                (item[1], item[2])
                                for item in ordered_mentions[:2]
                            ]

                        first_name, first_value = semantic_values[0]
                        second_name, second_value = semantic_values[1]

                        asks_ratio = any(
                            phrase in q
                            for phrase in (
                                "ratio",
                                "times as much",
                                "times higher",
                                "how many times",
                            )
                        )

                        asks_percentage_higher = any(
                            phrase in q
                            for phrase in (
                                "percentage higher",
                                "percent higher",
                                "% higher",
                            )
                        )

                        asks_percentage_lower = any(
                            phrase in q
                            for phrase in (
                                "percentage lower",
                                "percent lower",
                                "% lower",
                            )
                        )

                        asks_percentage_difference = any(
                            phrase in q
                            for phrase in (
                                "percentage difference",
                                "percent difference",
                            )
                        )

                        difference_requested = (
                            "difference between" in q
                            or "difference of" in q
                        )

                        if asks_ratio:
                            if second_value != 0:
                                ratio = first_value / second_value

                                answer = (
                                    f"The ratio of "
                                    f"{_readable(first_name)} to "
                                    f"{_readable(second_name)} is "
                                    f"{ratio:,.2f}."
                                )
                            else:
                                answer = (
                                    f"The ratio cannot be calculated "
                                    f"because {_readable(second_name)} "
                                    f"has a value of zero."
                                )

                        elif asks_percentage_higher:
                            if second_value != 0:
                                percentage = (
                                    (first_value - second_value)
                                    / abs(second_value)
                                ) * 100

                                if percentage >= 0:
                                    answer = (
                                        f"{_readable(first_name)} is "
                                        f"{percentage:,.2f}% higher than "
                                        f"{_readable(second_name)}."
                                    )
                                else:
                                    answer = (
                                        f"{_readable(first_name)} is "
                                        f"{abs(percentage):,.2f}% lower than "
                                        f"{_readable(second_name)}."
                                    )
                            else:
                                answer = (
                                    f"The percentage comparison cannot "
                                    f"be calculated because "
                                    f"{_readable(second_name)} "
                                    f"has a value of zero."
                                )

                        elif asks_percentage_lower:
                            if first_value != 0:
                                percentage = (
                                    (second_value - first_value)
                                    / abs(first_value)
                                ) * 100

                                if percentage >= 0:
                                    answer = (
                                        f"{_readable(first_name)} is "
                                        f"{percentage:,.2f}% lower than "
                                        f"{_readable(second_name)}."
                                    )
                                else:
                                    answer = (
                                        f"{_readable(first_name)} is "
                                        f"{abs(percentage):,.2f}% higher than "
                                        f"{_readable(second_name)}."
                                    )
                            else:
                                answer = (
                                    f"The percentage comparison cannot "
                                    f"be calculated because "
                                    f"{_readable(first_name)} "
                                    f"has a value of zero."
                                )

                        elif asks_percentage_difference:
                            denominator = (
                                abs(first_value) + abs(second_value)
                            ) / 2

                            if denominator != 0:
                                percentage = (
                                    abs(first_value - second_value)
                                    / denominator
                                ) * 100

                                answer = (
                                    f"The percentage difference between "
                                    f"{_readable(first_name)} and "
                                    f"{_readable(second_name)} is "
                                    f"{percentage:,.2f}%."
                                )
                            else:
                                answer = (
                                    f"The percentage difference cannot "
                                    f"be calculated because both values "
                                    f"are zero."
                                )

                        elif difference_requested:
                            difference = abs(
                                first_value - second_value
                            )

                            answer = (
                                f"The difference between the "
                                f"{label} of "
                                f"{_readable(first_name)} and "
                                f"{_readable(second_name)} is "
                                f"{difference:,.2f}."
                            )

                    if answer is None:
                        parts = [
                            f"{_readable(name)}: {value:,.2f}"
                            for name, value in values
                        ]

                        answer = (
                            f"The {label} comparison is: "
                            + "; ".join(parts)
                            + "."
                        )

                        asks_for_winner = any(
                            phrase in q
                            for phrase in (
                                "higher",
                                "lower",
                                "greater",
                                "less",
                                "which has",
                                "which is higher",
                                "which is lower",
                            )
                        )

                        if asks_for_winner:
                            highest = max(
                                values,
                                key=lambda item: item[1],
                            )
                            lowest = min(
                                values,
                                key=lambda item: item[1],
                            )

                            asks_lower = any(
                                phrase in q
                                for phrase in (
                                    "lower",
                                    "less",
                                    "smallest",
                                    "lowest",
                                )
                            )

                            asks_higher = any(
                                phrase in q
                                for phrase in (
                                    "higher",
                                    "greater",
                                    "largest",
                                    "highest",
                                )
                            )

                            if asks_lower and not asks_higher:
                                answer = (
                                    f"The lower {label} is "
                                    f"{_readable(lowest[0])} "
                                    f"at {lowest[1]:,.2f}."
                                )

                            elif asks_higher and not asks_lower:
                                answer = (
                                    f"The higher {label} is "
                                    f"{_readable(highest[0])} "
                                    f"at {highest[1]:,.2f}."
                                )

                            else:
                                answer = (
                                    f"The highest {label} is "
                                    f"{_readable(highest[0])} "
                                    f"at {highest[1]:,.2f}, "
                                    f"while the lowest is "
                                    f"{_readable(lowest[0])} "
                                    f"at {lowest[1]:,.2f}."
                                )

                    return _base_result(
                        question,
                        "comparison_analysis",
                        answer,
                        sql,
                        result_columns,
                        rows,
                        {
                            "type": "comparison",
                            "x": "",
                            "y": aliases,
                            "title": (
                                f"{label.title()} "
                                "Comparison"
                            ),
                        },
                    )

    # ------------------------------------------------------------
    # Single-column aggregation
    # ------------------------------------------------------------
    aggregation = _detect_aggregation(q)
    # ------------------------------------------------------------
    # Multi-column aggregation
    # ------------------------------------------------------------
    #
    # Examples:
    #   What is the average of Mathematics, Programming, and Data_Science?
    #   What is the sum of Revenue, Profit, and Cost?
    #   Give me the maximum of Sales and Revenue.
    #
    # Resolve every explicitly mentioned numeric column and aggregate
    # them independently. This is dataset-agnostic.
    # ------------------------------------------------------------

    if aggregation:
        mentioned_numeric = [
            column
            for column in _find_mentioned_columns(
                q,
                columns,
            )
            if column in numeric
        ]

        group_column = _detect_group_column(
            q,
            columns,
        )

        # Only use this path when multiple numeric metrics are
        # explicitly requested and the question is not grouped.
        if (
            len(mentioned_numeric) >= 2
            and group_column is None
        ):
            aliases = []
            expressions = []

            for metric_column in mentioned_numeric:
                readable_metric = _readable(
                    metric_column
                )

                safe_name = re.sub(
                    r"[^a-zA-Z0-9]+",
                    "_",
                    readable_metric,
                ).strip("_").lower()

                alias = (
                    f"{aggregation.lower()}_{safe_name}"
                )

                base_alias = alias
                suffix = 2

                while alias in aliases:
                    alias = (
                        f"{base_alias}_{suffix}"
                    )
                    suffix += 1

                aliases.append(alias)

                expressions.append(
                    f"{aggregation}("
                    f"TRY_CAST({_q(metric_column)} AS DOUBLE)"
                    f") AS {_q(alias)}"
                )

            sql = (
                "SELECT "
                + ", ".join(expressions)
                + " FROM main_table"
            )

            result_columns, rows = _execute(
                dataset,
                sql,
            )

            if not rows:
                return None

            row = rows[0]

            label = {
                "AVG": "average",
                "SUM": "sum",
                "MIN": "minimum",
                "MAX": "maximum",
                "MEDIAN": "median",
            }.get(
                aggregation,
                aggregation.lower(),
            )

            parts = []

            for metric_column, alias in zip(
                mentioned_numeric,
                aliases,
            ):
                value = row.get(alias)

                if value is None:
                    parts.append(
                        f"{_readable(metric_column)}: "
                        "no numeric value"
                    )
                    continue

                try:
                    value_float = float(value)

                    parts.append(
                        f"{_readable(metric_column)}: "
                        f"{value_float:,.2f}"
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    parts.append(
                        f"{_readable(metric_column)}: "
                        f"{value}"
                    )

            answer = (
                f"The {label} values are: "
                + "; ".join(parts)
                + "."
            )

            return _base_result(
                question,
                "local_query",
                answer,
                sql,
                result_columns,
                rows,
                {
                    "type": "multi_metric",
                    "x": "",
                    "y": aliases,
                    "title": (
                        f"{label.title()} "
                        "Across Selected Metrics"
                    ),
                },
            )


    if aggregation and not _detect_group_column(
        q,
        columns,
    ):
        metric = _detect_metric_column(
            q,
            columns,
            numeric,
        )

        # Explain invalid numeric operations on categorical fields instead
        # of falling through to a generic SQL/LLM fallback.
        if (
            aggregation in ("AVG", "SUM", "MIN", "MAX", "MEDIAN")
            and metric is None
        ):
            mentioned = _find_mentioned_columns(q, columns)
            categorical = [
                column for column in mentioned
                if column not in numeric
            ]
            if categorical:
                requested = ", ".join(_readable(column) for column in categorical)
                answer = (
                    f"{requested} is categorical text, so it cannot be "
                    "averaged or summed. Try counting records by that field, "
                    "or choose a numeric metric such as revenue, leads, "
                    "conversions, or cost."
                )
                return _base_result(
                    question,
                    "schema_validation",
                    answer,
                    "",
                    [],
                    [],
                    {"type": "table", "title": "Choose a numeric metric"},
                )

        if aggregation == "COUNT":
            target = (
                _q(metric)
                if metric
                else "*"
            )

            sql = (
                "SELECT COUNT("
                + target
                + ") AS count "
                "FROM main_table"
            )

            result_columns, rows = _execute(
                dataset,
                sql,
            )

            count = (
                int(rows[0]["count"])
                if rows and rows[0]["count"] is not None
                else 0
            )

            subject = (
                _readable(metric)
                if metric
                else "records"
            )

            return _base_result(
                question,
                "local_query",
                f"The count of {subject} is {count:,}.",
                sql,
                result_columns,
                rows,
                {
                    "type": "metric",
                    "x": "",
                    "y": "count",
                    "title": (
                        f"Count of "
                        f"{subject.title()}"
                    ),
                },
            )

        if metric:
            alias = (
                f"{aggregation.lower()}_value"
            )

            sql = (
                "SELECT "
                f"{aggregation}("
                f"TRY_CAST({_q(metric)} AS DOUBLE)"
                f") AS {_q(alias)} "
                "FROM main_table"
            )

            result_columns, rows = _execute(
                dataset,
                sql,
            )

            value = (
                rows[0][alias]
                if rows
                else None
            )

            if value is None:
                return None

            value_float = float(value)

            label = {
                "AVG": "average",
                "SUM": "sum",
                "MIN": "minimum",
                "MAX": "maximum",
                "MEDIAN": "median",
            }.get(
                aggregation,
                aggregation.lower(),
            )

            answer = (
                f"The {label} "
                f"{_readable(metric)} "
                f"is {value_float:,.2f}."
            )

            return _base_result(
                question,
                "local_query",
                answer,
                sql,
                result_columns,
                rows,
                {
                    "type": "metric",
                    "x": "",
                    "y": alias,
                    "title": (
                        f"{label.title()} "
                        f"{_readable(metric).title()}"
                    ),
                },
            )

    # ------------------------------------------------------------
    # Correlation
    # ------------------------------------------------------------
    if (
        "correlation" in q
        or "relationship between" in q
        or "related" in q
    ):
        mentioned = [
            column
            for column in _find_mentioned_columns(
                q,
                columns,
            )
            if column in numeric
        ]

        if len(mentioned) >= 2:
            first, second = mentioned[:2]

            sql = f"""
                SELECT corr(
                    TRY_CAST({_q(first)} AS DOUBLE),
                    TRY_CAST({_q(second)} AS DOUBLE)
                ) AS correlation
                FROM main_table
                WHERE {_q(first)} IS NOT NULL
                  AND {_q(second)} IS NOT NULL
            """

            result_columns, rows = _execute(
                dataset,
                sql,
            )

            if (
                rows
                and rows[0]["correlation"] is not None
            ):
                correlation = float(
                    rows[0]["correlation"]
                )

                answer = (
                    "The correlation between "
                    f"{_readable(first)} and "
                    f"{_readable(second)} is "
                    f"{correlation:.3f}."
                )

                return _base_result(
                    question,
                    "correlation_analysis",
                    answer,
                    sql,
                    result_columns,
                    rows,
                    {
                        "type": "scatter",
                        "x": first,
                        "y": second,
                        "title": (
                            f"{_readable(first)} "
                            "vs "
                            f"{_readable(second)}"
                        ),
                        "correlation": correlation,
                    },
                )

    return None



def _try_filtering_query(dataset, question):
    """
    Generic dataset-independent filtering engine.

    Supports natural-language conditions such as:

        Percentage greater than 80
        price below 100
        salary >= 50000
        age between 25 and 40
        score > 80 and attendance > 75

    The function resolves columns from the actual dataset schema and
    generates a safe DuckDB WHERE clause.
    """

    import re

    q = (question or "").strip()

    if not q:
        return None

    # ------------------------------------------------------------
    # Load actual dataset schema
    # ------------------------------------------------------------

    # Resolve schema from the Dataset abstraction first.
    # The current application stores column names directly in
    # dataset.columns and the DuckDB connection in dataset.con.
    columns = list(getattr(dataset, "columns", None) or [])

    # Fallback for DataFrame-backed dataset implementations.
    if not columns:
        try:
            columns = list(dataset.df.columns)
        except Exception:
            columns = []

    if not columns:
        return None

    # Normalize both the dataset column names and the question.
    #
    # This allows all of these to resolve to the same column:
    #
    #   Attendance_Percent
    #   Attendance Percent
    #   attendance_percent
    #   attendance percent
    #
    # The original column name is always retained for SQL generation.

    def normalize_identifier(value):
        value = str(value).strip().lower()
        value = re.sub(r"[_\-]+", " ", value)
        value = re.sub(r"\s+", " ", value)
        return value.strip()

    normalized = {
        normalize_identifier(column): str(column)
        for column in columns
    }

    # ------------------------------------------------------------
    # Resolve columns mentioned in the question
    # ------------------------------------------------------------

    mentioned = []

    q_lower = q.lower()
    q_normalized = normalize_identifier(q)

    for normalized_name, original_name in normalized.items():
        if not normalized_name:
            continue

        # Match against normalized natural-language form.
        if normalized_name in q_normalized:
            if original_name not in mentioned:
                mentioned.append(original_name)

        # Also support the literal schema spelling.
        elif str(original_name).lower() in q_lower:
            if original_name not in mentioned:
                mentioned.append(original_name)

    if not mentioned:
        return None

    # ------------------------------------------------------------
    # Detect condition phrases
    #
    # Work entirely with a normalized version of the question so
    # schema names such as:
    #
    #   Attendance_Percent
    #   Attendance Percent
    #   attendance_percent
    #
    # are treated consistently.
    # ------------------------------------------------------------

    q_condition = normalize_identifier(q)

    operator_patterns = [
        (r"greater than or equal to", ">="),
        (r"more than or equal to", ">="),
        (r"less than or equal to", "<="),
        (r"at least", ">="),
        (r"at most", "<="),
        (r"no more than", "<="),
        (r"not equal to", "!="),
        (r"greater than", ">"),
        (r"more than", ">"),
        (r"above", ">"),
        (r"over", ">"),
        (r"less than", "<"),
        (r"below", "<"),
        (r"under", "<"),
        (r"equal to", "="),
        (r"equals", "="),
    ]

    conditions = []

    # ------------------------------------------------------------
    # Extract a condition independently for EVERY mentioned column.
    # ------------------------------------------------------------

    for column in mentioned:
        normalized_column = normalize_identifier(column)

        if not normalized_column:
            continue

        # Escape the actual schema name for safe regex construction.
        column_pattern = re.escape(normalized_column)

        found = False

        # Natural-language operators:
        #
        #   Percentage greater than 80
        #   Attendance_Percent greater than 75
        #   score at least 70
        #
        for pattern, operator in operator_patterns:
            match = re.search(
                rf"(?<!\w){column_pattern}(?!\w)"
                rf"\s+{pattern}\s+"
                rf"(-?\d+(?:\.\d+)?)",
                q_condition,
                re.IGNORECASE,
            )

            if match:
                conditions.append(
                    (
                        column,
                        operator,
                        match.group(1),
                    )
                )
                found = True
                break

        if found:
            continue

        # --------------------------------------------------------
        # Symbolic operators:
        #
        #   Percentage > 80
        #   Attendance_Percent >= 75
        #   score <= 50
        # --------------------------------------------------------

        match = re.search(
            rf"(?<!\w){column_pattern}(?!\w)"
            rf"\s*(>=|<=|!=|<>|>|<|=)\s*"
            rf"(-?\d+(?:\.\d+)?)",
            q_condition,
            re.IGNORECASE,
        )

        if match:
            conditions.append(
                (
                    column,
                    match.group(1),
                    match.group(2),
                )
            )

    # ------------------------------------------------------------
    # Support "between X and Y" conditions.
    #
    # Example:
    #   Percentage between 70 and 90
    #
    # This becomes:
    #   Percentage >= 70
    #   Percentage <= 90
    # ------------------------------------------------------------

    between_pattern = re.compile(
        r"(?P<column>.+?)\s+between\s+"
        r"(?P<low>-?\d+(?:\.\d+)?)\s+and\s+"
        r"(?P<high>-?\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )

    for match in between_pattern.finditer(q_condition):
        expression = match.group(0)

        for column in mentioned:
            normalized_column = normalize_identifier(column)

            if re.search(
                rf"(?<!\w){re.escape(normalized_column)}(?!\w)",
                expression,
                re.IGNORECASE,
            ):
                conditions.append(
                    (
                        column,
                        ">=",
                        match.group("low"),
                    )
                )

                conditions.append(
                    (
                        column,
                        "<=",
                        match.group("high"),
                    )
                )

                break

    # ------------------------------------------------------------
    # Remove duplicate conditions while preserving order.
    # ------------------------------------------------------------

    unique_conditions = []
    seen_conditions = set()

    for condition in conditions:
        if condition not in seen_conditions:
            unique_conditions.append(condition)
            seen_conditions.add(condition)

    conditions = unique_conditions

    if not conditions:
        return None

    # ------------------------------------------------------------
    # Build WHERE clause
    # ------------------------------------------------------------

    def quote(identifier):
        return '"' + str(identifier).replace('"', '""') + '"'

    where_parts = []

    for column, operator, value in conditions:
        where_parts.append(
            f"TRY_CAST({quote(column)} AS DOUBLE) {operator} {value}"
        )

    where_clause = "\n        AND ".join(where_parts)

    # ------------------------------------------------------------
    # Decide whether the user wants a count or matching rows.
    # ------------------------------------------------------------

    count_request = any(
        phrase in q_lower
        for phrase in (
            "how many",
            "number of",
            "count",
            "count of",
            "how much",
        )
    )

    if count_request:
        sql = f"""
            SELECT COUNT(*) AS count
            FROM main_table
            WHERE {where_clause}
        """

        result_columns, rows = _execute(dataset, sql)

        if not rows:
            return None

        # _execute() normally returns dictionary-like rows.
        # Keep tuple/list compatibility for older execution paths.
        first_row = rows[0]

        if isinstance(first_row, dict):
            count = first_row.get("count")
        else:
            count = first_row[0]

        condition_text = " and ".join(
            f"{column} {operator} {value}"
            for column, operator, value in conditions
        )

        answer = (
            f"There are {int(count)} records matching "
            f"the condition(s): {condition_text}."
        )

        return {
            "answer": answer,
            "sql": sql.strip(),
            "columns": result_columns,
            "rows": rows,
            "model": "local",
            "fallback": None,
        }

    # ------------------------------------------------------------
    # Otherwise return matching records.
    # ------------------------------------------------------------

    sql = f"""
        SELECT *
        FROM main_table
        WHERE {where_clause}
        LIMIT 100
    """

    result_columns, rows = _execute(dataset, sql)

    return {
        "answer": (
            f"Found {len(rows)} matching records. "
            f"Showing up to 100 records."
        ),
        "sql": sql.strip(),
        "columns": result_columns,
        "rows": rows,
        "model": "local",
        "fallback": None,
    }


def _try_grouped_query(
    dataset: Dataset,
    question: str,
) -> dict | None:
    """
    Generic grouped aggregation and ranking engine.

    Handles:
      - count by Department
      - average CGPA by Department
      - which Department has the highest average CGPA
      - top 5 categories by average score
      - lowest/highest category metrics
    """
    q = _norm(question)
    columns = _columns(dataset)
    numeric = _numeric_columns(dataset)

    group = _detect_group_column(
        q,
        columns,
    )

    # Ranking questions frequently use:
    # "Which Department has the highest average CGPA?"
    # There is no "by Department" phrase, so infer the grouping
    # dimension from the explicitly mentioned non-numeric column.
    if group is None and any(
        phrase in q
        for phrase in (
            "which ",
            "what ",
            "highest ",
            "lowest ",
            "largest ",
            "smallest ",
            "top ",
            "bottom ",
        )
    ):
        mentioned = _find_mentioned_columns(
            q,
            columns,
        )

        non_numeric = [
            column
            for column in mentioned
            if column not in numeric
        ]

        if non_numeric:
            group = non_numeric[0]

    if not group:
        return None

    aggregation = _detect_aggregation(q)
    # In grouped rankings, "highest total revenue" means the group with
    # the largest SUM(revenue), not MAX(revenue) within each group.
    if re.search(r"\\b(?:highest|largest|most)\\s+total\\b", q):
        aggregation = "SUM"
    elif re.search(r"\\b(?:highest|largest|most)\\s+average\\b", q):
        aggregation = "AVG"
    # ------------------------------------------------------------
    # Multi-column aggregation
    # ------------------------------------------------------------
    #
    # Examples:
    #   What is the average of Mathematics, Programming, and Data_Science?
    #   What is the sum of Revenue, Profit, and Cost?
    #   Give me the maximum of Sales and Revenue.
    #
    # Resolve every explicitly mentioned numeric column and aggregate
    # them independently. This is dataset-agnostic.
    # ------------------------------------------------------------

    if aggregation:
        mentioned_numeric = [
            column
            for column in _find_mentioned_columns(
                q,
                columns,
            )
            if column in numeric
        ]

        group_column = _detect_group_column(
            q,
            columns,
        )

        # Only use this path when multiple numeric metrics are
        # explicitly requested and the question is not grouped.
        if (
            len(mentioned_numeric) >= 2
            and group_column is None
        ):
            aliases = []
            expressions = []

            for metric_column in mentioned_numeric:
                readable_metric = _readable(
                    metric_column
                )

                safe_name = re.sub(
                    r"[^a-zA-Z0-9]+",
                    "_",
                    readable_metric,
                ).strip("_").lower()

                alias = (
                    f"{aggregation.lower()}_{safe_name}"
                )

                base_alias = alias
                suffix = 2

                while alias in aliases:
                    alias = (
                        f"{base_alias}_{suffix}"
                    )
                    suffix += 1

                aliases.append(alias)

                expressions.append(
                    f"{aggregation}("
                    f"TRY_CAST({_q(metric_column)} AS DOUBLE)"
                    f") AS {_q(alias)}"
                )

            sql = (
                "SELECT "
                + ", ".join(expressions)
                + " FROM main_table"
            )

            result_columns, rows = _execute(
                dataset,
                sql,
            )

            if not rows:
                return None

            row = rows[0]

            label = {
                "AVG": "average",
                "SUM": "sum",
                "MIN": "minimum",
                "MAX": "maximum",
                "MEDIAN": "median",
            }.get(
                aggregation,
                aggregation.lower(),
            )

            parts = []

            for metric_column, alias in zip(
                mentioned_numeric,
                aliases,
            ):
                value = row.get(alias)

                if value is None:
                    parts.append(
                        f"{_readable(metric_column)}: "
                        "no numeric value"
                    )
                    continue

                try:
                    value_float = float(value)

                    parts.append(
                        f"{_readable(metric_column)}: "
                        f"{value_float:,.2f}"
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    parts.append(
                        f"{_readable(metric_column)}: "
                        f"{value}"
                    )

            answer = (
                f"The {label} values are: "
                + "; ".join(parts)
                + "."
            )

            return _base_result(
                question,
                "local_query",
                answer,
                sql,
                result_columns,
                rows,
                {
                    "type": "multi_metric",
                    "x": "",
                    "y": aliases,
                    "title": (
                        f"{label.title()} "
                        "Across Selected Metrics"
                    ),
                },
            )


    count_mode = (
        aggregation == "COUNT"
        or any(
            phrase in q
            for phrase in (
                "how many",
                "number of",
                "count",
            )
        )
    )

    metric = _detect_metric_column(
        q,
        columns,
        numeric,
        exclude=group,
    )
    # ------------------------------------------------------------
    # Generic scalar MAX/MIN metric resolution
    # ------------------------------------------------------------
    scalar_maxmin_language = any(
        re.search(
            r"\b" + re.escape(word) + r"\b",
            q,
            re.IGNORECASE,
        )
        for word in (
            "highest",
            "lowest",
            "maximum",
            "minimum",
        )
    )

    if metric is None and scalar_maxmin_language:
        metric_text = q

        metric_text = re.sub(
            r"\b(?:what\s+is|what's|tell\s+me|show\s+me|find|get|give\s+me)\b",
            " ",
            metric_text,
            flags=re.IGNORECASE,
        )

        metric_text = re.sub(
            r"\b(?:highest|lowest|maximum|minimum)\b",
            " ",
            metric_text,
            flags=re.IGNORECASE,
        )

        metric_text = re.sub(
            r"\b(?:value|amount|number)\b",
            " ",
            metric_text,
            flags=re.IGNORECASE,
        )

        metric_text = re.sub(r"\s+", " ", metric_text).strip()

        metric = _resolve_column(
            metric_text,
            columns,
            numeric_only=True,
            numeric=numeric,
        )

        if metric is not None:
            if re.search(
                r"\b(?:highest|maximum)\b",
                q,
                re.IGNORECASE,
            ):
                aggregation = "MAX"
            elif re.search(
                r"\b(?:lowest|minimum)\b",
                q,
                re.IGNORECASE,
            ):
                aggregation = "MIN"


    # ------------------------------------------------------------
    # Requested metric is not represented by the dataset schema.
    #
    # Example:
    #   "Which Department has the highest average CGPA?"
    #
    # If CGPA does not exist, do NOT call Gemini and do NOT
    # silently substitute another metric such as Percentage.
    # Return a schema-aware response instead.
    # ------------------------------------------------------------
    metric_language = any(
        phrase in q
        for phrase in (
            "average",
            "avg",
            "mean",
            "sum",
            "total",
            "highest",
            "lowest",
            "maximum",
            "minimum",
            "median",
            "top",
            "bottom",
        )
    )

    if (
        metric is None
        and not count_mode
        and metric_language
    ):
        available_numeric = [
            _readable(column)
            for column in numeric
        ]

        if available_numeric:
            available_text = ", ".join(
                available_numeric[:12]
            )

            if len(available_numeric) > 12:
                available_text += ", ..."

            answer = (
                "I cannot answer this question because "
                "the requested metric is not available "
                "in the dataset schema. "
                f"Available numeric fields include: "
                f"{available_text}."
            )
        else:
            answer = (
                "I cannot answer this question because "
                "the requested metric is not available "
                "in the dataset schema."
            )

        return _base_result(
            question,
            "schema_validation",
            answer,
            None,
            [],
            [],
        )

    # Explicit ranking phrases define AVG when the question says
    # "highest average" / "lowest average".
    if any(
        phrase in q
        for phrase in (
            "highest average",
            "lowest average",
            "highest mean",
            "lowest mean",
        )
    ):
        aggregation = "AVG"

    if not aggregation and metric:
        # In business-style "show revenue by region" questions, totals are
        # the expected interpretation. Keep AVG as the neutral default for
        # ordinary statistical datasets.
        metric_name = _norm(metric)
        revenue_cost_fields = {
            "revenue", "net revenue", "sales", "turnover", "income",
            "profit", "net profit", "gross profit",
            "cost", "spend", "expense", "expenses",
            "marketing spend", "units sold", "quantity", "units",
            "returns", "returned units",
        }
        aggregation = "SUM" if metric_name in revenue_cost_fields else "AVG"

    if not aggregation:
        return None

    # ------------------------------------------------------------
    # Grouped row counts
    # ------------------------------------------------------------
    if count_mode and not metric:
        sql = f"""
            SELECT
                {_q(group)} AS {_q(group)},
                COUNT(*) AS count
            FROM main_table
            WHERE {_q(group)} IS NOT NULL
            GROUP BY {_q(group)}
            ORDER BY count DESC
        """

        result_columns, rows = _execute(
            dataset,
            sql,
        )

        lines = [
            f"{row[group]}: "
            f"{int(row['count']):,}"
            for row in rows
        ]

        answer = (
            f"The number of records in each "
            f"{_readable(group)} is:\n"
            + "\n".join(lines)
        )

        return _base_result(
            question,
            "local_grouped_analysis",
            answer,
            sql,
            result_columns,
            rows,
            {
                "type": "bar",
                "x": group,
                "y": "count",
                "title": (
                    f"Count by "
                    f"{_readable(group).title()}"
                ),
            },
        )

    if not metric:
        return None

    # ------------------------------------------------------------
    # Ranking / top-N vs ordinary grouped aggregation
    # ------------------------------------------------------------
    ranking_intent = any(
        phrase in q
        for phrase in (
            "highest",
            "lowest",
            "largest",
            "smallest",
            "best",
            "worst",
            "most",
            "least",
            "maximum",
            "minimum",
            "leading",
            "ranked",
            "ranking",
            "rank",
        )
    )

    top_match = re.search(
        r"\b(?:top|bottom)\s+(\d+)",
        q,
    )

    ranking_intent = ranking_intent or bool(top_match)

    # ------------------------------------------------------------
    # Explicit sort direction
    # ------------------------------------------------------------
    #
    # Default:
    #   DESC
    #
    # Explicit ascending:
    #   ascending / asc
    #
    # Explicit descending:
    #   descending / desc
    #
    # Ranking language such as highest/top/best remains DESC,
    # while lowest/bottom/worst remains ASC.
    # ------------------------------------------------------------
    explicit_ascending = bool(
        re.search(
            r"\b(?:ascending|asc)(?:\s+order)?\b",
            q,
            re.IGNORECASE,
        )
    )

    explicit_descending = bool(
        re.search(
            r"\b(?:descending|desc)(?:\s+order)?\b",
            q,
            re.IGNORECASE,
        )
    )

    if explicit_ascending:
        order = "ASC"
    elif explicit_descending:
        order = "DESC"
    else:
        descending = not any(
            phrase in q
            for phrase in (
                "lowest",
                "smallest",
                "bottom",
                "least",
                "worst",
            )
        )

        order = "DESC" if descending else "ASC"

    # Normal grouped aggregations return every group.
    # Ranking questions return only the requested top/bottom group(s).
    limit_clause = ""

    if ranking_intent:
        limit = 1

        if top_match:
            limit = max(
                1,
                min(
                    int(top_match.group(1)),
                    100,
                ),
            )

        limit_clause = f"LIMIT {limit}"

    alias = "value"

    sql = f"""
        SELECT
            {_q(group)} AS {_q(group)},
            {aggregation}(
                TRY_CAST({_q(metric)} AS DOUBLE)
            ) AS {alias}
        FROM main_table
        WHERE {_q(group)} IS NOT NULL
        GROUP BY {_q(group)}
        ORDER BY {alias} {order}
        {limit_clause}
    """

    result_columns, rows = _execute(
        dataset,
        sql,
    )

    if not rows:
        return None

    label = {
        "AVG": "average",
        "SUM": "sum",
        "MIN": "minimum",
        "MAX": "maximum",
        "MEDIAN": "median",
        "COUNT": "count",
    }.get(
        aggregation,
        aggregation.lower(),
    )

    # A single ranking answer gets a natural sentence.
    if (
        len(rows) == 1
        and any(
            phrase in q
            for phrase in (
                "which ",
                "what ",
                "highest",
                "lowest",
                "top",
                "bottom",
            )
        )
    ):
        row = rows[0]
        value = _safe_float(
            row[alias]
        )

        value_text = (
            f"{value:,.2f}"
            if value is not None
            else str(row[alias])
        )

        if ranking_intent and len(rows) == 1:
            ranking_word = "highest" if descending else "lowest"

            answer = (
                f"{row[group]} has the "
                f"{ranking_word} {label} "
                f"{_readable(metric)} "
                f"at {value_text}."
            )
        else:
            answer = (
                f"{row[group]} has the "
                f"{label} {_readable(metric)} "
                f"at {value_text}."
            )
    else:
        lines = []

        for row in rows:
            value = _safe_float(
                row[alias]
            )

            if value is None:
                lines.append(
                    f"{row[group]}: "
                    f"{row[alias]}"
                )
            else:
                lines.append(
                    f"{row[group]}: "
                    f"{value:,.2f}"
                )

        answer = (
            f"The {label} "
            f"{_readable(metric)} by "
            f"{_readable(group)} is:\n"
            + "\n".join(lines)
        )

    return _base_result(
        question,
        "local_grouped_analysis",
        answer,
        sql,
        result_columns,
        rows,
        {
            "type": "bar",
            "x": group,
            "y": alias,
            "title": (
                f"{label.title()} "
                f"{_readable(metric).title()} by "
                f"{_readable(group).title()}"
            ),
        },
    )


def _try_statistical_query(
    dataset: Dataset,
    question: str,
) -> dict | None:
    q = _norm(question)

    if not any(
        phrase in q
        for phrase in (
            "standard deviation",
            "std",
            "variance",
            "statistics",
            "statistical summary",
            "quartile",
            "percentile",
        )
    ):
        return None

    columns = _columns(dataset)
    numeric = _numeric_columns(dataset)

    mentioned = [
        column
        for column in _find_mentioned_columns(
            q,
            columns,
        )
        if column in numeric
    ]

    if mentioned:
        metric = mentioned[0]
    elif len(numeric) == 1:
        metric = numeric[0]
    else:
        return None

    sql = f"""
        SELECT
            COUNT({_q(metric)}) AS count,
            AVG(
                TRY_CAST({_q(metric)} AS DOUBLE)
            ) AS mean,
            STDDEV_SAMP(
                TRY_CAST({_q(metric)} AS DOUBLE)
            ) AS stddev,
            VAR_SAMP(
                TRY_CAST({_q(metric)} AS DOUBLE)
            ) AS variance,
            MIN(
                TRY_CAST({_q(metric)} AS DOUBLE)
            ) AS min,
            MEDIAN(
                TRY_CAST({_q(metric)} AS DOUBLE)
            ) AS median,
            MAX(
                TRY_CAST({_q(metric)} AS DOUBLE)
            ) AS max,
            quantile_cont(
                TRY_CAST({_q(metric)} AS DOUBLE),
                0.25
            ) AS q1,
            quantile_cont(
                TRY_CAST({_q(metric)} AS DOUBLE),
                0.75
            ) AS q3
        FROM main_table
    """

    result_columns, rows = _execute(
        dataset,
        sql,
    )

    if not rows:
        return None

    row = rows[0]

    def fmt(name: str) -> str:
        value = _safe_float(
            row.get(name)
        )

        if value is None:
            return "N/A"

        return f"{value:.2f}"

    answer = (
        f"Statistics for {_readable(metric)}: "
        f"count={row['count']}, "
        f"mean={fmt('mean')}, "
        f"stddev={fmt('stddev')}, "
        f"min={fmt('min')}, "
        f"median={fmt('median')}, "
        f"max={fmt('max')}, "
        f"Q1={fmt('q1')}, "
        f"Q3={fmt('q3')}."
    )

    return _base_result(
        question,
        "statistical_analysis",
        answer,
        sql,
        result_columns,
        rows,
    )


def _try_percentage_query(
    dataset: Dataset,
    question: str,
) -> dict | None:
    """
    Handle percentage/share questions generically.

    Two fundamentally different cases are supported:

    1. Record-share questions:
       "What percentage of students are in each Department?"
       "What percentage of customers are in each Region?"
       "What percentage of records are in each Category?"

       These use COUNT(*) / total COUNT(*).

    2. Numeric-metric share questions:
       "What percentage of revenue comes from each Region?"
       "What is the share of sales by Category?"

       These use SUM(metric) / total SUM(metric).

    The distinction is made from the question and dataset schema,
    without hardcoding any specific dataset columns.
    """

    q = _norm(question)

    percentage_words = (
        "percentage",
        "percent",
        "%",
        "share",
        "proportion",
    )

    if not any(
        phrase in q
        for phrase in percentage_words
    ):
        return None

    columns = _columns(dataset)
    numeric = _numeric_columns(dataset)

    group = _detect_group_column(
        q,
        columns,
    )

    if not group:
        return None

    # ------------------------------------------------------------
    # Detect whether the question refers to records/entities
    # rather than a numeric metric.
    # ------------------------------------------------------------

    record_words = (
        "student",
        "students",
        "customer",
        "customers",
        "client",
        "clients",
        "employee",
        "employees",
        "person",
        "people",
        "patient",
        "patients",
        "user",
        "users",
        "record",
        "records",
        "row",
        "rows",
        "entry",
        "entries",
        "observation",
        "observations",
        "transaction",
        "transactions",
        "item",
        "items",
        "product",
        "products",
        "application",
        "applications",
        "order",
        "orders",
    )

    record_share_intent = any(
        word in q
        for word in record_words
    )

    # ------------------------------------------------------------
    # Detect an explicitly requested numeric metric.
    # ------------------------------------------------------------

    metric = _detect_metric_column(
        q,
        columns,
        numeric,
        exclude=group,
    )

    # ------------------------------------------------------------
    # Record percentage:
    #
    # "What percentage of students are in each Department?"
    #
    # IMPORTANT:
    # Do NOT use a numeric column merely because the word
    # "percentage" appears in its name.
    # ------------------------------------------------------------

    if record_share_intent:
        sql = f"""
            SELECT
                {_q(group)} AS {_q(group)},
                COUNT(*) AS count,
                COUNT(*) * 100.0
                    / NULLIF(
                        (
                            SELECT COUNT(*)
                            FROM main_table
                            WHERE {_q(group)} IS NOT NULL
                        ),
                        0
                    ) AS percentage
            FROM main_table
            WHERE {_q(group)} IS NOT NULL
            GROUP BY {_q(group)}
            ORDER BY percentage DESC
        """

        result_columns, rows = _execute(
            dataset,
            sql,
        )

        answer = (
            f"The percentage of records by "
            f"{_readable(group)} is:\n"
            + "\n".join(
                f"{row[group]}: "
                f"{_safe_float(row['percentage']):.2f}%"
                for row in rows
            )
        )

        return _base_result(
            question,
            "percentage_analysis",
            answer,
            sql,
            result_columns,
            rows,
            {
                "type": "pie",
                "x": group,
                "y": "percentage",
                "title": (
                    f"Percentage of Records by "
                    f"{_readable(group).title()}"
                ),
            },
        )

    # ------------------------------------------------------------
    # Numeric metric share:
    #
    # "What percentage of revenue comes from each Region?"
    # "What is the sales share by Category?"
    # ------------------------------------------------------------

    if metric:
        share_language = any(
            phrase in q
            for phrase in (
                "share",
                "percentage",
                "percent",
                "%",
                "proportion",
            )
        )

        if share_language:
            sql = f"""
                WITH grouped AS (
                    SELECT
                        {_q(group)} AS {_q(group)},
                        SUM(
                            TRY_CAST({_q(metric)} AS DOUBLE)
                        ) AS value
                    FROM main_table
                    WHERE {_q(group)} IS NOT NULL
                    GROUP BY {_q(group)}
                ),
                totals AS (
                    SELECT SUM(value) AS total
                    FROM grouped
                )
                SELECT
                    {_q(group)},
                    value,
                    CASE
                        WHEN total = 0 THEN 0
                        ELSE value * 100.0 / total
                    END AS percentage
                FROM grouped
                CROSS JOIN totals
                ORDER BY percentage DESC
            """

            result_columns, rows = _execute(
                dataset,
                sql,
            )

            answer = (
                f"The {_readable(metric)} share by "
                f"{_readable(group)} is:\n"
                + "\n".join(
                    f"{row[group]}: "
                    f"{_safe_float(row['percentage']):.2f}%"
                    for row in rows
                )
            )

            return _base_result(
                question,
                "percentage_analysis",
                answer,
                sql,
                result_columns,
                rows,
                {
                    "type": "pie",
                    "x": group,
                    "y": "percentage",
                    "title": (
                        f"{_readable(metric).title()} "
                        f"Share by "
                        f"{_readable(group).title()}"
                    ),
                },
            )

    return None


def _try_derived_metric_query(
    dataset: Dataset,
    question: str,
) -> dict | None:
    """Calculate common business KPIs only from semantically matched columns."""
    q = _norm(question)
    columns = _columns(dataset)
    numeric = _numeric_columns(dataset)

    def resolve(aliases):
        # Prefer exact normalized column names, then unambiguous aliases.
        for column in columns:
            if _norm(column) in aliases and column in numeric:
                return column
        matches = [column for column in columns if column in numeric and any(
            alias in _norm(column).split() or _norm(column) == alias
            for alias in aliases
        )]
        return matches[0] if len(matches) == 1 else None

    revenue = resolve({"revenue", "sales", "income", "turnover"})
    cost = resolve({"cost", "spend", "expense", "expenses", "marketing cost", "marketing spend"})
    leads = resolve({"lead", "leads"})
    conversions = resolve({"conversion", "conversions", "converted", "orders"})

    intent = None
    if "return on investment" in q or re.search(r"\broi\b", q):
        intent = "roi"
        required = (revenue, cost)
        expression = f"(SUM(TRY_CAST({_q(revenue)} AS DOUBLE)) - SUM(TRY_CAST({_q(cost)} AS DOUBLE))) * 100.0 / NULLIF(SUM(TRY_CAST({_q(cost)} AS DOUBLE)), 0)" if all(required) else None
        label = "ROI"
        suffix = "%"
    elif "profit margin" in q:
        intent = "profit_margin"
        required = (revenue, cost)
        expression = f"(SUM(TRY_CAST({_q(revenue)} AS DOUBLE)) - SUM(TRY_CAST({_q(cost)} AS DOUBLE))) * 100.0 / NULLIF(SUM(TRY_CAST({_q(revenue)} AS DOUBLE)), 0)" if all(required) else None
        label, suffix = "Profit margin", "%"
    elif "conversion rate" in q or "lead conversion" in q:
        intent = "conversion_rate"
        required = (conversions, leads)
        expression = f"SUM(TRY_CAST({_q(conversions)} AS DOUBLE)) * 100.0 / NULLIF(SUM(TRY_CAST({_q(leads)} AS DOUBLE)), 0)" if all(required) else None
        label, suffix = "Conversion rate", "%"
    elif "cost per lead" in q or re.search(r"\bcpl\b", q):
        intent = "cost_per_lead"
        required = (cost, leads)
        expression = f"SUM(TRY_CAST({_q(cost)} AS DOUBLE)) / NULLIF(SUM(TRY_CAST({_q(leads)} AS DOUBLE)), 0)" if all(required) else None
        label, suffix = "Cost per lead", ""
    elif "revenue per conversion" in q:
        intent = "revenue_per_conversion"
        required = (revenue, conversions)
        expression = f"SUM(TRY_CAST({_q(revenue)} AS DOUBLE)) / NULLIF(SUM(TRY_CAST({_q(conversions)} AS DOUBLE)), 0)" if all(required) else None
        label, suffix = "Revenue per conversion", ""
    elif "profit" in q:
        intent = "profit"
        required = (revenue, cost)
        expression = f"SUM(TRY_CAST({_q(revenue)} AS DOUBLE)) - SUM(TRY_CAST({_q(cost)} AS DOUBLE))" if all(required) else None
        label, suffix = "Profit", ""
    else:
        return None

    if not expression:
        available = [name for name, col in (("revenue/sales", revenue), ("cost/spend", cost), ("leads", leads), ("conversions", conversions)) if col]
        return _base_result(
            question, "unsupported_metric",
            f"I can't calculate {label.lower()} reliably because the required source columns are missing or ambiguous. Matched columns: {', '.join(available) if available else 'none'}.",
            "", [], [], {"type": "table", "title": "Required source columns"},
        )

    group = _detect_group_column(q, columns)
    group_sql = f", {_q(group)} AS {_q(group)}" if group else ""
    group_by = f" GROUP BY {_q(group)} ORDER BY value DESC" if group else ""
    sql = f"SELECT {expression} AS value{group_sql} FROM main_table{group_by}"
    result_columns, rows = _execute(dataset, sql)
    if not rows:
        return None

    def fmt(value):
        if value is None:
            return "N/A"
        return f"{float(value):,.2f}{suffix}"

    if group:
        summary = "; ".join(f"{row.get(group)}: {fmt(row.get('value'))}" for row in rows)
        answer = f"{label} by {_readable(group)}: {summary}."
    else:
        answer = f"{label}: {fmt(rows[0].get('value'))}."

    return _base_result(
        question, "derived_metric", answer, sql, result_columns, rows,
        {"type": "bar" if group else "metric", "x": group or "", "y": "value", "title": f"{label} by {_readable(group)}" if group else label},
        metric_name=intent,
    )


def _try_anomaly_query(
    dataset: Dataset,
    question: str,
) -> dict | None:
    q = _norm(question)

    if not any(
        phrase in q
        for phrase in (
            "outlier",
            "anomal",
            "unusual",
        )
    ):
        return None

    columns = _columns(dataset)
    numeric = _numeric_columns(dataset)

    mentioned = [
        column
        for column in _find_mentioned_columns(
            q,
            columns,
        )
        if column in numeric
    ]

    if mentioned:
        metric = mentioned[0]
    elif len(numeric) == 1:
        metric = numeric[0]
    else:
        return None

    sql = f"""
        WITH stats AS (
            SELECT
                quantile_cont(
                    TRY_CAST({_q(metric)} AS DOUBLE),
                    0.25
                ) AS q1,
                quantile_cont(
                    TRY_CAST({_q(metric)} AS DOUBLE),
                    0.75
                ) AS q3
            FROM main_table
        )
        SELECT
            main_table.*,
            q1,
            q3
        FROM main_table
        CROSS JOIN stats
        WHERE
            TRY_CAST({_q(metric)} AS DOUBLE)
                < q1 - 1.5 * (q3 - q1)
            OR
            TRY_CAST({_q(metric)} AS DOUBLE)
                > q3 + 1.5 * (q3 - q1)
    """

    result_columns, rows = _execute(
        dataset,
        sql,
    )

    answer = (
        f"Found {len(rows)} IQR-based "
        f"outlier record(s) for "
        f"{_readable(metric)}."
    )

    return _base_result(
        question,
        "anomaly_detection",
        answer,
        sql,
        result_columns,
        rows,
        {
            "type": "table",
            "x": "",
            "y": "",
            "title": (
                f"Outliers in "
                f"{_readable(metric).title()}"
            ),
        },
    )


def _try_trend_query(
    dataset: Dataset,
    question: str,
) -> dict | None:
    """Aggregate a numeric metric at the requested calendar grain."""
    q = _norm(question)
    dates = _date_columns(dataset)
    if not dates:
        return None

    if not any(phrase in q for phrase in (
        "trend", "over time", "time series", "monthly", "daily",
        "weekly", "yearly", "historical trend", "growth over time",
    )):
        return None

    columns = _columns(dataset)
    numeric = _numeric_columns(dataset)
    date_column = dates[0]
    metric = _detect_metric_column(q, columns, numeric)
    if not metric:
        return None

    if any(word in q for word in ("monthly", "by month", "per month")):
        grain = "month"
    elif any(word in q for word in ("weekly", "by week", "per week")):
        grain = "week"
    elif any(word in q for word in ("yearly", "annually", "by year", "per year")):
        grain = "year"
    elif any(word in q for word in ("daily", "by day", "per day")):
        grain = "day"
    else:
        grain = "day"

    aggregation = _detect_aggregation(q)
    aggregate_sql = "AVG" if aggregation == "AVG" else "SUM"
    period_sql = f"DATE_TRUNC('{grain}', TRY_CAST({_q(date_column)} AS DATE))"
    sql = f"""
        SELECT
            {period_sql} AS period,
            {aggregate_sql}(TRY_CAST({_q(metric)} AS DOUBLE)) AS value
        FROM main_table
        WHERE TRY_CAST({_q(date_column)} AS DATE) IS NOT NULL
        GROUP BY period
        ORDER BY period
    """
    result_columns, rows = _execute(dataset, sql)
    if not rows:
        return None

    grain_label = {"day": "Daily", "week": "Weekly", "month": "Monthly", "year": "Yearly"}[grain]
    aggregation_label = "average" if aggregate_sql == "AVG" else "total"
    return _base_result(
        question,
        "trend_analysis",
        f"{grain_label} {aggregation_label} {_readable(metric)} is shown in the result.",
        sql,
        result_columns,
        rows,
        {"type": "line", "x": "period", "y": "value",
         "title": f"{grain_label} { _readable(metric).title() }"},
    )


def _try_forecast_query(
    dataset: Dataset,
    question: str,
) -> dict | None:
    """
    Forecasting intentionally falls through to the Gemini planner.
    The deterministic engine does not fabricate a forecasting model.
    """
    q = _norm(question)

    if not any(
        phrase in q
        for phrase in (
            "forecast",
            "predict next",
            "future value",
            "projected",
        )
    ):
        return None

    return None


def _try_main_insight_query(
    dataset: Dataset,
    question: str,
) -> dict | None:
    """Build an evidence-based executive summary from the uploaded schema."""
    q = _norm(question)
    if not any(phrase in q for phrase in (
        "insight", "key finding", "main finding",
        "important finding", "summary", "takeaway", "conclude",
    )):
        return None

    columns = _columns(dataset)
    numeric = _numeric_columns(dataset)
    if not numeric:
        return None

    # Resolve only fields that genuinely exist. Do not manufacture leads,
    # conversions, campaigns, or a generic "cost" from unrelated columns.
    def actual(*names):
        wanted = {_norm(name) for name in names}
        return next((column for column in columns if _norm(column) in wanted), None)

    revenue = actual("revenue", "gross revenue", "sales")
    net_revenue = actual("net_revenue", "net revenue", "net sales")
    profit = actual("profit", "net profit", "gross profit")
    marketing_spend = actual(
        "marketing_spend", "marketing spend", "advertising spend", "ad spend"
    )
    cost = actual("cost", "total cost", "expenses", "expense")
    units = actual("units_sold", "units sold", "quantity", "units")
    returns = actual("returns", "returned units", "return units")
    rating = actual("customer_rating", "customer rating", "rating")
    region = actual("region", "territory", "area")
    team = actual("team")
    campaign = actual("campaign", "campaign name")
    leads = actual("leads", "lead")
    conversions = actual("conversions", "conversion")
    product = actual("product", "product name", "item")
    channel = actual("channel", "sales channel")

    if not any((revenue, net_revenue, profit)):
        return None

    expressions = ["COUNT(*) AS record_count"]
    fields = {
        "total_revenue": revenue,
        "total_net_revenue": net_revenue,
        "total_profit": profit,
        "total_marketing_spend": marketing_spend,
        "total_cost": cost,
        "total_units_sold": units,
        "total_returns": returns,
        "total_leads": leads,
        "total_conversions": conversions,
    }
    for alias, column in fields.items():
        if column:
            expressions.append(
                f"SUM(TRY_CAST({_q(column)} AS DOUBLE)) AS {_q(alias)}"
            )
    if rating:
        expressions.append(
            f"AVG(TRY_CAST({_q(rating)} AS DOUBLE)) AS average_customer_rating"
        )

    summary_sql = "SELECT " + ", ".join(expressions) + " FROM main_table"
    _, summary_rows = _execute(dataset, summary_sql)
    if not summary_rows:
        return None

    summary = summary_rows[0]
    record_count = int(summary.get("record_count") or 0)
    total_revenue = _safe_float(summary.get("total_revenue"))
    total_net_revenue = _safe_float(summary.get("total_net_revenue"))
    total_profit = _safe_float(summary.get("total_profit"))
    total_marketing_spend = _safe_float(summary.get("total_marketing_spend"))
    total_cost = _safe_float(summary.get("total_cost"))
    total_units = _safe_float(summary.get("total_units_sold"))
    total_returns = _safe_float(summary.get("total_returns"))
    total_leads = _safe_float(summary.get("total_leads"))
    total_conversions = _safe_float(summary.get("total_conversions"))
    average_rating = _safe_float(summary.get("average_customer_rating"))

    # Legacy funnel datasets may have revenue and cost but no stored profit.
    if total_profit is None and total_revenue is not None and total_cost is not None:
        total_profit = total_revenue - total_cost

    # Weighted margin: ratio of aggregate profit to aggregate net revenue.
    margin_base = total_net_revenue or total_revenue
    profit_margin = (
        total_profit * 100.0 / margin_base
        if total_profit is not None and margin_base
        else None
    )
    return_rate = (
        total_returns * 100.0 / total_units
        if total_returns is not None and total_units
        else None
    )
    profit_to_marketing = (
        total_profit / total_marketing_spend
        if total_profit is not None and total_marketing_spend
        else None
    )
    roi = (
        total_profit * 100.0 / total_cost
        if total_profit is not None and total_cost
        else None
    )
    conversion_rate = (
        total_conversions * 100.0 / total_leads
        if total_conversions is not None and total_leads
        else None
    )

    findings = [
        f"The dataset contains {record_count:,} transaction records."
    ]
    if total_revenue is not None:
        findings.append(f"Gross revenue totals {total_revenue:,.2f}.")
    if total_net_revenue is not None:
        findings.append(f"Net revenue after returns/adjustments totals {total_net_revenue:,.2f}.")
    if total_profit is not None:
        findings.append(f"Recorded profit totals {total_profit:,.2f}.")
    if roi is not None:
        findings.append(f"Profit-based ROI against recorded cost is {roi:.2f}%.")
    if conversion_rate is not None:
        findings.append(
            f"Overall conversion rate is {conversion_rate:.2f}% "
            f"({total_conversions:,.0f} conversions from {total_leads:,.0f} leads)."
        )
    if profit_margin is not None:
        findings.append(f"Weighted profit margin is {profit_margin:.2f}%.")
    if total_marketing_spend is not None:
        findings.append(f"Marketing spend totals {total_marketing_spend:,.2f}.")
    if profit_to_marketing is not None:
        findings.append(
            f"Profit is {profit_to_marketing:.2f} times marketing spend "
            "(this is a profit-to-marketing-spend ratio, not an attributed marketing ROI)."
        )
    if total_returns is not None and total_units:
        findings.append(
            f"Return rate by units is {return_rate:.2f}% "
            f"({total_returns:,.0f} returned units from {total_units:,.0f} units sold)."
        )
    if average_rating is not None:
        findings.append(f"Average customer rating is {average_rating:.2f} out of 5.")

    result_rows = [{
        "records": record_count,
        **({"total_revenue": total_revenue} if total_revenue is not None else {}),
        **({"total_net_revenue": total_net_revenue} if total_net_revenue is not None else {}),
        **({"total_profit": total_profit} if total_profit is not None else {}),
        **({"roi_percent": roi} if roi is not None else {}),
        **({"total_leads": total_leads} if total_leads is not None else {}),
        **({"total_conversions": total_conversions} if total_conversions is not None else {}),
        **({"conversion_rate_percent": conversion_rate} if conversion_rate is not None else {}),
        **({"profit_margin_percent": profit_margin} if profit_margin is not None else {}),
        **({"total_marketing_spend": total_marketing_spend} if total_marketing_spend is not None else {}),
        **({"profit_to_marketing_spend_ratio": profit_to_marketing} if profit_to_marketing is not None else {}),
        **({"return_rate_percent": return_rate} if return_rate is not None else {}),
        **({"average_customer_rating": average_rating} if average_rating is not None else {}),
    }]

    # Identify the leading categories using sums, not row-level averages.
    for dimension, label in (
        (region or team, "region" if region else "team"),
        (product, "product"),
        (channel, "channel"),
        (campaign, "campaign"),
    ):
        metric_column = revenue or net_revenue or profit
        if not dimension or not metric_column:
            continue
        sql = f"""
            SELECT {_q(dimension)} AS label,
                   SUM(TRY_CAST({_q(metric_column)} AS DOUBLE)) AS metric_value
            FROM main_table
            WHERE {_q(dimension)} IS NOT NULL
            GROUP BY {_q(dimension)}
            ORDER BY metric_value DESC
            LIMIT 1
        """
        _, rows = _execute(dataset, sql)
        if rows:
            leader = rows[0]
            findings.append(
                f"Leading {label} by { _readable(metric_column) } is "
                f"{leader.get('label')} at "
                f"{(_safe_float(leader.get('metric_value')) or 0.0):,.2f}."
            )

    # For the campaign/leads demo schema, identify the campaign with the
    # strongest profit-based ROI without applying that formula to marketing
    # spend datasets where cost attribution is not defined.
    if campaign and revenue and cost:
        roi_sql = f"""
            SELECT {_q(campaign)} AS label,
                   (SUM(TRY_CAST({_q(revenue)} AS DOUBLE))
                    - SUM(TRY_CAST({_q(cost)} AS DOUBLE))) * 100.0
                    / NULLIF(SUM(TRY_CAST({_q(cost)} AS DOUBLE)), 0) AS roi
            FROM main_table
            WHERE {_q(campaign)} IS NOT NULL
            GROUP BY {_q(campaign)}
            ORDER BY roi DESC
            LIMIT 1
        """
        _, roi_rows = _execute(dataset, roi_sql)
        if roi_rows:
            findings.append(
                f"Highest-ROI campaign is {roi_rows[0].get('label')} "
                f"at {(_safe_float(roi_rows[0].get('roi')) or 0.0):,.2f}%."
            )

    answer = " ".join(findings)
    display_columns = list(result_rows[0].keys())
    chart_metric = (
        "total_revenue" if total_revenue is not None
        else "total_net_revenue" if total_net_revenue is not None
        else "total_profit"
    )
    return _base_result(
        question,
        "main_insight",
        answer,
        summary_sql,
        display_columns,
        result_rows,
        {
            "type": "metric",
            "title": "Executive business summary",
            "x": "",
            "y": chart_metric,
        },
        key_findings=findings,
    )


# ============================================================================
# Compatibility wrappers
# ============================================================================

def _try_business_insight_query(
    dataset: Dataset,
    question: str,
) -> dict | None:
    """
    Compatibility name retained for AnalystAgent.
    It now delegates to the generic grouped engine.
    """
    return _try_grouped_query(
        dataset,
        question,
    )


def _try_numeric_query(
    dataset: Dataset,
    question: str,
) -> dict | None:
    """
    Compatibility name retained for AnalystAgent.
    """
    return _try_local_query(
        dataset,
        question,
    )


# ============================================================================
# Conversation / contextual follow-ups
# ============================================================================

def _normalize_conversation_history(
    history,
) -> list[dict]:
    if not history:
        return []

    normalized = []

    for item in history:
        if not isinstance(item, dict):
            continue

        role = item.get("role")
        text = item.get("text")

        if (
            role not in ("user", "assistant")
            or not isinstance(text, str)
            or not text.strip()
        ):
            continue

        entry = {
            "role": role,
            "text": text.strip(),
        }

        if item.get("result") is not None:
            entry["result"] = item["result"]
        else:
            # Preserve the result shape emitted by frontend/src/components/AIAnalyst.jsx.
            for key in ("rows", "columns", "sql", "visualization", "resultType", "type", "model", "agent"):
                if key in item:
                    entry[key] = item[key]

        normalized.append(entry)

    return normalized


def _try_contextual_followup(
    dataset: Dataset,
    question: str,
    conversation_history: list[dict] | None = None,
) -> dict | None:
    """Explain the most recent assistant result using its actual rows and metadata."""
    history = _normalize_conversation_history(conversation_history)
    if not history:
        return None

    q = _norm(question)
    if not any(marker in q for marker in (
        "why", "explain", "what does that", "what about", "and what",
        "how about", "tell me more", "summarize", "interpret",
    )):
        return None

    previous = next(
        (item for item in reversed(history) if item.get("role") == "assistant"),
        None,
    )
    if not previous:
        return None

    previous_result = previous.get("result")
    if not isinstance(previous_result, dict):
        previous_result = {
            "answer": previous.get("text", ""),
            "rows": previous.get("rows", []),
            "sql": previous.get("sql", ""),
            "columns": previous.get("columns", []),
            "visualization": previous.get("visualization"),
            "type": previous.get("resultType") or previous.get("type"),
        }

    rows = previous_result.get("rows", [])
    if not isinstance(rows, list):
        return None
    rows = [row for row in rows if isinstance(row, dict)]
    prior_answer = str(previous_result.get("answer") or "").strip()
    visualization = previous_result.get("visualization") or {}
    sql = str(previous_result.get("sql") or "")

    def numeric_value(value):
        try:
            number = float(value)
            return number if math.isfinite(number) else None
        except (TypeError, ValueError):
            return None

    explanation_parts = []
    x_key = visualization.get("x") if isinstance(visualization, dict) else None
    y_key = visualization.get("y") if isinstance(visualization, dict) else None

    if rows:
        keys = list(rows[0].keys())
        if not x_key:
            x_key = next((key for key in keys if numeric_value(rows[0].get(key)) is None), None)
        if not y_key or y_key not in rows[0]:
            y_key = next((key for key in keys if key != x_key and numeric_value(rows[0].get(key)) is not None), None)

        if x_key and y_key and y_key in rows[0]:
            ranked = [
                (row.get(x_key), numeric_value(row.get(y_key)))
                for row in rows
                if numeric_value(row.get(y_key)) is not None
            ]
            if ranked:
                ranked.sort(key=lambda item: item[1], reverse=True)
                total = sum(value for _, value in ranked)
                top_label, top_value = ranked[0]
                explanation_parts.append(
                    f"The strongest group is {top_label}, with {top_value:,.2f} "
                    f"for { _readable(y_key) }."
                )
                if len(ranked) > 1:
                    low_label, low_value = ranked[-1]
                    explanation_parts.append(
                        f"The lowest group is {low_label} at {low_value:,.2f}."
                    )
                if total > 0:
                    share = top_value * 100.0 / total
                    explanation_parts.append(
                        f"The leading group represents {share:.1f}% of the displayed group total."
                    )
                aggregation_label = "summed" if re.search(r"\bSUM\s*\(", sql, re.I) else (
                    "averaged" if re.search(r"\bAVG\s*\(", sql, re.I) else "compared"
                )
                explanation_parts.append(
                    f"The analysis {aggregation_label} { _readable(y_key) } "
                    f"across { _readable(x_key) } groups."
                )
        elif len(rows) == 1:
            values = [
                f"{_readable(key)} = {value:,.2f}"
                for key, raw in rows[0].items()
                if (value := numeric_value(raw)) is not None
            ]
            if values:
                explanation_parts.append(
                    "The result is a dataset-wide metric: " + ", ".join(values[:5]) + "."
                )
                if re.search(r"\bSUM\s*\(", sql, re.I):
                    explanation_parts.append("It is calculated by adding the qualifying values across the dataset.")
                elif re.search(r"\bAVG\s*\(", sql, re.I):
                    explanation_parts.append("It is calculated as the arithmetic average of the qualifying values.")
        else:
            explanation_parts.append(
                f"The previous query returned {len(rows):,} rows. "
                f"The first result contains: {', '.join(keys[:6])}."
            )

    if prior_answer:
        explanation_parts.insert(0, f"The previous analysis found: {prior_answer}")
    if not explanation_parts:
        explanation_parts.append(
            "I can see the previous question, but it did not include structured result rows to explain. "
            "Please rerun that analysis so I can explain its figures."
        )

    answer = " ".join(explanation_parts)
    return _base_result(
        question,
        "contextual_followup",
        answer,
        sql,
        previous_result.get("columns") or (list(rows[0].keys()) if rows else []),
        rows,
        visualization if isinstance(visualization, dict) else None,
        explained_result_type=previous_result.get("type"),
    )


def _try_contextual_dimension_ranking(
    dataset: Dataset,
    question: str,
    conversation_history: list[dict] | None = None,
) -> dict | None:
    """Resolve generic 'which category contributes most?' from the prior chart."""
    q = _norm(question)
    if not (
        ("which " in q or "what " in q)
        and any(phrase in q for phrase in (
            "contributes most", "contributes the most", "largest contribution",
            "highest contribution", "biggest contribution",
        ))
    ):
        return None

    history = _normalize_conversation_history(conversation_history)
    previous = next(
        (item for item in reversed(history) if item.get("role") == "assistant"),
        None,
    )
    if not previous:
        return None

    visualization = previous.get("visualization") or {}
    group = visualization.get("x") if isinstance(visualization, dict) else None
    if not group or group not in _columns(dataset):
        return None

    numeric = _numeric_columns(dataset)
    columns = _columns(dataset)
    y_key = visualization.get("y") if isinstance(visualization, dict) else None

    previous_user = next(
        (item for item in reversed(history) if item.get("role") == "user"),
        None,
    )
    metric = None
    if previous_user:
        metric = _detect_metric_column(previous_user.get("text", ""), columns, numeric)
    if metric is None and y_key in numeric:
        metric = y_key
    if metric is None:
        title = visualization.get("title", "") if isinstance(visualization, dict) else ""
        metric = _detect_metric_column(title, columns, numeric)
    if metric is None:
        # Only infer a business metric when revenue/sales is unambiguous.
        revenue_candidates = [
            column for column in numeric
            if _norm(column) in {"revenue", "sales", "turnover", "income"}
        ]
        if len(revenue_candidates) == 1:
            metric = revenue_candidates[0]

    if metric is None:
        return None

    synthetic_question = (
        f"Which {_readable(group)} has the highest total {_readable(metric)}?"
    )
    result = _try_grouped_query(dataset, synthetic_question)
    if result is None:
        return None

    result["question"] = question
    result["type"] = "contextual_followup"
    result["followup_for"] = previous.get("text", "")
    result["answer"] = (
        f"Based on the previous chart, I ranked {_readable(group)} by total "
        f"{_readable(metric)}. " + result.get("answer", "")
    )
    return result


# ============================================================================
# Gemini fallback
# ============================================================================

def _schema_text(dataset: Dataset) -> str:
    lines = [
        f"Dataset: {getattr(dataset, 'filename', 'dataset')}",
        f"Rows: {getattr(dataset, 'row_count', '?')}",
        "Columns:",
    ]

    for item in _schema(dataset):
        lines.append(
            f'- "{item["name"]}" ({item["type"]})'
        )

    return "\n".join(lines)


def _conversation_text(history) -> str:
    normalized = _normalize_conversation_history(
        history
    )

    if not normalized:
        return "No previous conversation."

    lines = []

    for item in normalized[-6:]:
        lines.append(
            f'{item["role"].title()}: '
            f'{item["text"]}'
        )

    return "\n".join(lines)


def _generate_sql(
    dataset: Dataset,
    question: str,
    conversation_history: list[dict] | None = None,
) -> str:
    if _client is None:
        raise RuntimeError(
            "Gemini is not configured."
        )

    prompt = f"""
You are the generic SQL planning engine for an AI Data Analyst application.

TABLE:
main_table

SCHEMA:
{_schema_text(dataset)}

RECENT CONVERSATION:
{_conversation_text(conversation_history)}

CURRENT QUESTION:
{question}

TASK:
Determine whether the question can be answered using the supplied schema.

If the question can be answered using the available columns:
Return exactly ONE valid read-only DuckDB SQL query.

If the question requires a column or concept that does NOT exist in the
schema and cannot be safely mapped to an existing column by exact name
or clear semantic equivalence:
Return exactly:

UNANSWERABLE

RULES:
1. Query only main_table.
2. Use only columns present in the schema.
3. Never invent a column.
4. Never silently substitute one metric for another.
5. Do not assume that similarly named metrics are equivalent.
6. Quote column names with double quotes.
7. Use TRY_CAST(... AS DOUBLE) for numeric calculations where useful.
8. Return one SQL statement only when the question is answerable.
9. SELECT and WITH ... SELECT are allowed.
10. Never use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE,
    COPY, ATTACH, DETACH, INSTALL, LOAD, or PRAGMA.
11. Return either SQL only or the exact word UNANSWERABLE.
"""

    response = _client.models.generate_content(
        model=MODEL,
        contents=prompt,
    )

    text = getattr(
        response,
        "text",
        None,
    )

    raw_text = str(text or "").strip()

    # Gemini may explicitly report that the requested concept
    # is not represented by the dataset schema.
    if raw_text.upper().strip("`* \n\r\t") == "UNANSWERABLE":
        return "UNANSWERABLE"

    sql = _clean_sql(
        raw_text
    )

    if not _is_read_only_sql(sql):
        raise ValueError(
            "Generated SQL failed read-only validation."
        )

    return sql


def _gemini_result(
    dataset: Dataset,
    question: str,
    conversation_history=None,
) -> dict | None:
    try:
        sql = _generate_sql(
            dataset,
            question,
            conversation_history,
        )

        # The SQL planner can explicitly report that the requested
        # concept is not represented by the dataset schema.
        if sql.strip().upper() == "UNANSWERABLE":
            columns = _columns(dataset)

            numeric = _numeric_columns(dataset)

            readable_numeric = [
                _readable(column)
                for column in numeric
            ]

            if readable_numeric:
                available = ", ".join(
                    readable_numeric[:12]
                )

                if len(readable_numeric) > 12:
                    available += ", ..."

                answer = (
                    "I cannot answer this question because "
                    "the requested field or concept is not "
                    "available in the dataset schema. "
                    f"Available numeric fields include: "
                    f"{available}."
                )
            else:
                answer = (
                    "I cannot answer this question because "
                    "the requested field or concept is not "
                    "available in the dataset schema."
                )

            return _base_result(
                question,
                "llm_analysis",
                answer,
                None,
                [],
                [],
            )

        result_columns, rows = _execute(
            dataset,
            sql,
        )

        if not rows:
            answer = (
                "The query executed successfully "
                "but returned no rows."
            )

        elif (
            len(rows) == 1
            and len(rows[0]) == 1
        ):
            value = next(
                iter(rows[0].values())
            )

            if isinstance(
                value,
                float,
            ):
                answer = (
                    f"The result is "
                    f"{value:,.2f}."
                )
            else:
                answer = (
                    f"The result is "
                    f"{value}."
                )

        else:
            preview = rows[:10]
            answer = (
                f"The analysis returned "
                f"{len(rows)} row(s). "
                f"Here are the first results: "
                f"{preview}"
            )

        return _base_result(
            question,
            "llm_analysis",
            answer,
            sql,
            result_columns,
            rows,
        )

    except Exception as exc:
        print(
            "Gemini fallback error:",
            repr(exc),
        )
        return None


# ============================================================================
# Main compatibility entry point
# ============================================================================

def analyze_with_llm(
    dataset: Dataset,
    question: str,
    conversation_history: list[dict] | None = None,
) -> dict:
    """
    Main entry point used by FastAPI / AnalystAgent.

    The order is intentionally generic:
      1. contextual follow-up
      2. simple numeric/local query
      3. grouped/ranking query
      4. percentage/share
      5. anomaly
      6. statistics
      7. trend
      8. generic insight
      9. Gemini SQL fallback
    """
    if (
        not isinstance(question, str)
        or not question.strip()
    ):
        raise ValueError(
            "Question must be a non-empty string."
        )

    started = time.perf_counter()
    question = question.strip()

    history = _normalize_conversation_history(
        conversation_history
    )

    engines = [
        ("derived_metrics", lambda: _try_derived_metric_query(dataset, question)),
        (
            "contextual_followup",
            lambda: _try_contextual_followup(
                dataset,
                question,
                history,
            ),
        ),
        (
            "local_query",
            lambda: _try_local_query(
                dataset,
                question,
            ),
        ),
        (
            "grouped_analysis",
            lambda: _try_grouped_query(
                dataset,
                question,
            ),
        ),
        (
            "percentage_analysis",
            lambda: _try_percentage_query(
                dataset,
                question,
            ),
        ),
        (
            "anomaly_detection",
            lambda: _try_anomaly_query(
                dataset,
                question,
            ),
        ),
        (
            "statistics",
            lambda: _try_statistical_query(
                dataset,
                question,
            ),
        ),
        (
            "trend",
            lambda: _try_trend_query(
                dataset,
                question,
            ),
        ),
        (
            "main_insight",
            lambda: _try_main_insight_query(
                dataset,
                question,
            ),
        ),
    ]

    errors = []

    for name, engine in engines:
        try:
            result = engine()

            if result is not None:
                result["agent"] = {
                    "name": (
                        "AI Data Analyst Agent"
                    ),
                    "plan": [
                        {
                            "tool": name,
                            "purpose": (
                                "Generic "
                                "dataset analysis"
                            ),
                            "status": "success",
                        }
                    ],
                    "total_duration_ms": round(
                        (
                            time.perf_counter()
                            - started
                        )
                        * 1000,
                        2,
                    ),
                    "fallback_used": False,
                }

                return result

        except Exception as exc:
            errors.append(
                (
                    name,
                    repr(exc),
                )
            )

            print(
                f"Analyst engine "
                f"{name} failed:",
                repr(exc),
            )

    # Final generic SQL fallback.
    result = _gemini_result(
        dataset,
        question,
        history,
    )

    if result is not None:
        result["agent"] = {
            "name": (
                "AI Data Analyst Agent"
            ),
            "plan": [
                {
                    "tool": "gemini_sql",
                    "purpose": (
                        "Generic SQL fallback"
                    ),
                    "status": "success",
                }
            ],
            "total_duration_ms": round(
                (
                    time.perf_counter()
                    - started
                )
                * 1000,
                2,
            ),
            "fallback_used": True,
        }

        return result

    details = "; ".join(
        f"{name}: {error}"
        for name, error in errors[-5:]
    )

    raise RuntimeError(
        "Unable to answer the question "
        "with the available analysis engines. "
        + details
    )


# Some older callers use this alias.
analyze = analyze_with_llm






