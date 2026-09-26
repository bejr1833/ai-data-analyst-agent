from pathlib import Path

path = Path("app/services/llm_analyst.py")
text = path.read_text(encoding="utf-8")

old = """    if is_explanation:
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
            "columns": (
                list(previous_rows[0].keys())
                if previous_rows
                and isinstance(previous_rows[0], dict)
                else []
            ),
            "rows": previous_rows,
            "row_count": len(previous_rows),
            "model": "local",
            "visualization": previous_visualization,
        }
"""

new = """    if is_explanation:
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
                    r'SUM\s*\(\s*["`]?([A-Za-z_][A-Za-z0-9_]*)',
                    previous_sql,
                    re.IGNORECASE,
                )
                avg_match = re.search(
                    r'AVG\s*\(\s*["`]?([A-Za-z_][A-Za-z0-9_]*)',
                    previous_sql,
                    re.IGNORECASE,
                )

                if sum_match:
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
            "columns": (
                list(previous_rows[0].keys())
                if previous_rows
                and isinstance(previous_rows[0], dict)
                else []
            ),
            "rows": previous_rows,
            "row_count": len(previous_rows),
            "model": "local",
            "visualization": previous_visualization,
        }
"""

if old not in text:
    raise SystemExit(
        "Could not find the current fast-path explanation block. "
        "No changes were made."
    )

backup = path.with_suffix(".py.before_contextual_fix.bak")
backup.write_text(text, encoding="utf-8")
path.write_text(text.replace(old, new, 1), encoding="utf-8")

print("SUCCESS: contextual explanation updated.")
print(f"Backup created: {backup}")
