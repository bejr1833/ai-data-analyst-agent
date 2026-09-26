
"""
Agentic AI Data Analyst orchestration layer.

Architecture:
    Question -> Planner -> Tool Executor -> Validator -> Synthesizer

The planner is deterministic/local-first so common analytics do not consume
Gemini quota. Gemini remains available through the existing general-analysis
fallback in llm_analyst.py.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, asdict
from typing import Callable


@dataclass
class AgentStep:
    tool: str
    purpose: str
    status: str = "pending"
    duration_ms: float = 0.0
    error: str | None = None


class AnalystAgent:
    """Planner/executor/validator around the project's existing analysis tools."""

    def __init__(self, dataset):
        from app.services import llm_analyst

        self.dataset = dataset
        self.llm = llm_analyst

        self.tools: dict[str, Callable | None] = {
            "local_query": getattr(llm_analyst, "_try_local_query", None),
            "forecast": getattr(llm_analyst, "_try_forecast_query", None),
            "trend": getattr(llm_analyst, "_try_trend_query", None),
            "statistics": getattr(llm_analyst, "_try_statistical_query", None),
            "business_insight": getattr(
                llm_analyst, "_try_business_insight_query", None
            ),
            "main_insight": getattr(
                llm_analyst, "_try_main_insight_query", None
            ),
            "grouped_analysis": getattr(llm_analyst, "_try_grouped_query", None),
            "numeric_analysis": getattr(llm_analyst, "_try_numeric_query", None),
            "anomaly_detection": getattr(
                llm_analyst, "_try_anomaly_query", None
            ),
            "data_quality": self._run_data_quality,
            "contextual_followup": getattr(
                llm_analyst, "_try_contextual_followup", None
            ),
        }

    def plan(self, question: str) -> list[AgentStep]:
        q = question.lower().strip()

        # Conversational follow-ups must be planned before generic
        # local_query/numeric analysis. The actual context resolver is
        # executed first in run(), but exposing it in the plan also makes
        # the agent trace accurately describe what happened.
        if self._contains_any(
            q,
            [
                "can you explain",
                "could you explain",
                "please explain",
                "explain that",
                "explain this",
                "explain it",
                "what does that mean",
                "what does this mean",
                "what does it mean",
                "tell me more",
                "how did you calculate that",
                "how was that calculated",
                "how did you get that",
            ],
        ):
            return [AgentStep(
                "contextual_followup",
                "Explain the previous analysis using conversation context",
            )]

        # Explicit Top-N/Bottom-N requests are rankings.
        if re.search(r"\b(?:top|bottom)\s+\d+\b", q):
            return [AgentStep(
                "business_insight",
                "Return the requested Top-N/Bottom-N ranking",
            )]

        if self._contains_any(
            q,
            [
                "what if", "suppose", "scenario", "impact if", "effect if",
                "increase by", "decrease by",
            ],
        ):
            return [AgentStep("scenario", "Run scenario/what-if analysis")]

        if self._contains_any(
            q,
            [
                "forecast", "predict", "prediction", "future",
                "next week", "next month", "next quarter", "next year",
            ],
        ):
            return [AgentStep("forecast", "Forecast a future metric")]

        if self._contains_any(
            q,
            [
                "anomaly", "anomalies", "outlier", "outliers",
                "unusual", "abnormal", "unexpected", "irregular",
            ],
        ):
            return [AgentStep("anomaly_detection", "Detect unusual observations")]

        if self._contains_any(
            q,
            [
                "data quality",
                "data-quality",
                "data profile",
                "data profiling",
                "quality summary",
                "missing values",
                "missing data",
                "null values",
                "null count",
                "duplicates",
                "duplicate rows",
                "data completeness",
            ],
        ):
            return [
                AgentStep(
                    "data_quality",
                    "Profile completeness, nulls, duplicates, and distinct values",
                )
            ]

        if self._contains_any(
            q,
            [
                "correlation", "median", "standard deviation", "variance",
                "percentile", "distribution", "statistics",
            ],
        ):
            return [AgentStep("statistics", "Run statistical analysis")]

        if self._contains_any(
            q,
            [
                "trend", "over time", "time series", "historical trend",
                "growth over time", "monthly trend", "daily trend",
            ],
        ):
            return [AgentStep("trend", "Analyze the metric over time")]

        if self._contains_any(
            q,
            [
                "main insight",
                "key insight",
                "main takeaway",
                "key takeaway",
                "give me an insight",
                "give me insights",
                "what can you conclude",
            ],
        ):
            return [AgentStep(
                "main_insight",
                "Identify the most important pattern in the dataset",
            )]

        if self._contains_any(
            q,
            [
                "highest", "lowest", "top", "best", "worst",
                "maximum", "minimum", "leading", "largest", "smallest",
            ],
        ):
            return [AgentStep(
                "business_insight",
                "Find a business ranking/insight",
            )]

        if (
            " by " in q
            or self._contains_any(
                q,
                [
                    "per region", "per product", "per category",
                    "per month", "per year", "per customer", "grouped",
                ],
            )
        ):
            return [AgentStep(
                "grouped_analysis",
                "Group a metric by a dimension",
            )]

        if self._contains_any(
            q,
            [
                "total", "sum", "average", "avg", "mean", "count",
                "how many", "maximum", "minimum",
            ],
        ):
            return [AgentStep(
                "numeric_analysis",
                "Compute a numeric metric",
            )]

        return [AgentStep(
            "local_query",
            "Try a deterministic local dataset query first",
        )]

    def run(
        self,
        question: str,
        conversation_history: list[dict] | None = None,
    ) -> dict:
        question = (question or "").strip()

        if not question:
            raise ValueError("Question cannot be empty.")

        started = time.perf_counter()
        steps = self.plan(question)

        print("\n==============================")
        print("AGENTIC DATA ANALYST")
        print("Question:", question)
        print("Plan:", " -> ".join(step.tool for step in steps))
        print("==============================")

        result = None

        # ----------------------------------------------------
        # Contextual follow-up gets absolute priority.
        # A recognized follow-up must never fall through to the
        # Gemini/general SQL fallback.
        # ----------------------------------------------------
        contextual_requested = False

        if conversation_history and isinstance(question, str):
            q_lower = question.lower().strip()

            contextual_phrases = [
                "explain that",
                "explain this",
                "explain it",
                "explain these results",
                "explain the results",
                "can you explain",
                "could you explain",
                "please explain",
                "what does that mean",
                "what does this mean",
                "what does it mean",
                "tell me more",
                "why is that",
                "why is this",
                "how did you calculate that",
                "how was that calculated",
                "how did you get that",
                "summarize these results",
                "summarize the results",
            ]

            contextual_requested = any(
                phrase in q_lower
                for phrase in contextual_phrases
            )

        if contextual_requested:
            contextual_tool = getattr(
                self.llm,
                "_try_contextual_followup",
                None,
            )

            if contextual_tool is not None:
                contextual_started = time.perf_counter()

                try:
                    contextual_result = contextual_tool(
                        self.dataset,
                        question,
                        conversation_history,
                    )

                    if contextual_result is not None:
                        result = contextual_result
                        steps = [
                            AgentStep(
                                "contextual_followup",
                                "Interpret the current question using the previous analysis result",
                                status="success",
                                duration_ms=round(
                                    (time.perf_counter() - contextual_started) * 1000,
                                    2,
                                ),
                            )
                        ]

                        print(
                            "Agent: contextual follow-up handled locally."
                        )

                except Exception as exc:
                    print(
                        "Contextual follow-up failed:",
                        repr(exc),
                    )
                    result = None

        # ----------------------------------------------------
        # Last-resort local contextual response.
        #
        # This is deliberately before the normal tool loop and
        # before Gemini. If the contextual helper fails for any
        # reason, use the previous assistant response directly.
        # ----------------------------------------------------
        if result is None and contextual_requested:
            previous_assistant = None

            for message in reversed(conversation_history or []):
                if not isinstance(message, dict):
                    continue

                if message.get("role") == "assistant":
                    previous_assistant = message
                    break

            if previous_assistant:
                previous_text = str(
                    previous_assistant.get("text")
                    or previous_assistant.get("content")
                    or previous_assistant.get("answer")
                    or ""
                ).strip()

                previous_rows = previous_assistant.get("rows")
                if not isinstance(previous_rows, list):
                    previous_rows = []

                if previous_text or previous_rows:
                    answer = (
                        "The previous analysis returned: "
                        f"{previous_text}"
                    )

                    if previous_rows:
                        answer += (
                            f" The analysis returned "
                            f"{len(previous_rows):,} result row"
                            + ("" if len(previous_rows) == 1 else "s")
                            + "."
                        )

                    result = {
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
                        "visualization": previous_assistant.get(
                            "visualization"
                        ),
                    }

                    steps = [
                        AgentStep(
                            "contextual_followup",
                            "Return the previous analysis locally without SQL/Gemini",
                            status="success",
                            duration_ms=0.0,
                        )
                    ]

                    print(
                        "Agent: contextual follow-up handled by local fallback."
                    )

        if result is None:
            for step in steps:
                started_step = time.perf_counter()

                try:
                    if step.tool == "scenario":
                        result = self._run_scenario(question)
                    elif step.tool == "contextual_followup":
                        tool = self.tools.get(step.tool)
                        if tool is not None:
                            result = tool(
                                self.dataset,
                                question,
                                conversation_history,
                            )
                        else:
                            result = None
                    else:
                        tool = self.tools.get(step.tool)

                        if tool is None:
                            step.status = "unavailable"
                            continue

                        result = tool(self.dataset, question)

                    step.duration_ms = round(
                        (time.perf_counter() - started_step) * 1000,
                        2,
                    )
                    step.status = "success" if result is not None else "no_result"

                except Exception as exc:
                    step.duration_ms = round(
                        (time.perf_counter() - started_step) * 1000,
                        2,
                    )
                    step.status = "failed"
                    step.error = str(exc)
                    print(f"Tool {step.tool} failed:", repr(exc))

                if result is not None:
                    break
        if result is None:
            print("Agent: using general SQL fallback.")
            try:
                result = self.llm.analyze_with_llm(
                    self.dataset,
                    question,
                    conversation_history=conversation_history,
                )
            except TypeError:
                # Backward compatibility with older llm_analyst.py.
                result = self.llm.analyze_with_llm(
                    self.dataset,
                    question,
                )

        result = self._validate_result(result, question)

        result["agent"] = {
            "name": "AI Data Analyst Agent",
            "plan": [asdict(step) for step in steps],
            "total_duration_ms": round(
                (time.perf_counter() - started) * 1000,
                2,
            ),
            "fallback_used": result.get("model") != "local",
        }

        print("Agent result type:", result.get("type"))
        print("Agent model:", result.get("model"))
        print("Agent total:", result["agent"]["total_duration_ms"], "ms")
        print("==============================\n")

        return result

    @staticmethod
    def _validate_result(result: dict, question: str) -> dict:
        if not isinstance(result, dict):
            raise ValueError("Agent tool returned an invalid response.")

        result.setdefault("question", question)
        # Normalize missing/None result types.
        # setdefault() does not replace an existing None value.
        if not result.get("type"):
            result["type"] = "analysis"
        result.setdefault("answer", "No answer was returned.")
        result.setdefault("rows", [])
        result.setdefault("columns", [])
        result.setdefault("row_count", len(result["rows"]))
        result.setdefault("model", "local")

        if not isinstance(result["rows"], list):
            result["rows"] = []

        if (
            result.get("visualization") is not None
            and not isinstance(result["visualization"], dict)
        ):
            result["visualization"] = None

        # A single numeric aggregate is displayed as a metric card, not
        # a generic table. This keeps the API contract consistent for
        # questions such as "What is the total revenue?"
        if (
            result.get("visualization") is None
            or result.get("visualization", {}).get("type") == "table"
        ):
            rows = result.get("rows") or []
            if (
                len(rows) == 1
                and isinstance(rows[0], dict)
                and any(
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    for value in rows[0].values()
                )
                and str(result.get("type", "")).lower()
                in {"numeric", "aggregate", "analysis", "metric", ""}
            ):
                result["visualization"] = {
                    "type": "metric",
                    "title": result.get("question") or question,
                }

        return result

    @staticmethod
    def _contains_any(text: str, words: list[str]) -> bool:
        return any(word in text for word in words)

    def _run_data_quality(self, dataset, question: str):
        """
        Deterministic data-quality summary.

        Returns dataset-level quality metrics plus per-column
        null, distinct, and completeness information.
        """

        if dataset is None or getattr(dataset, "con", None) is None:
            return None

        con = dataset.con

        try:
            total_rows = int(
                con.execute(
                    "SELECT COUNT(*) FROM main_table"
                ).fetchone()[0]
            )

            columns_result = con.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'main_table'
                ORDER BY ordinal_position
                """
            ).fetchall()

            column_names = [
                str(row[0])
                for row in columns_result
            ]

            total_columns = len(column_names)

            distinct_rows = int(
                con.execute(
                    """
                    SELECT COUNT(*)
                    FROM (
                        SELECT DISTINCT *
                        FROM main_table
                    ) AS distinct_data
                    """
                ).fetchone()[0]
            )

            duplicate_rows = max(
                0,
                total_rows - distinct_rows,
            )

            rows = []
            total_nulls = 0

            for column in column_names:
                safe_column = column.replace(
                    '"',
                    '""',
                )

                result = con.execute(
                    f'''
                    SELECT
                        COUNT(*) AS total_rows,
                        COUNT(*) - COUNT("{safe_column}") AS null_count,
                        COUNT(DISTINCT "{safe_column}") AS distinct_count
                    FROM main_table
                    '''
                ).fetchone()

                column_total = int(result[0] or 0)
                null_count = int(result[1] or 0)
                distinct_count = int(result[2] or 0)

                total_nulls += null_count

                completeness = (
                    100.0
                    if column_total == 0
                    else (
                        (column_total - null_count)
                        / column_total
                    ) * 100.0
                )

                rows.append(
                    {
                        "column_name": column,
                        "total_rows": column_total,
                        "null_count": null_count,
                        "distinct_count": distinct_count,
                        "completeness_pct": round(
                            completeness,
                            1,
                        ),
                    }
                )

            total_cells = total_rows * total_columns

            overall_completeness = (
                100.0
                if total_cells == 0
                else (
                    (total_cells - total_nulls)
                    / total_cells
                ) * 100.0
            )

            if total_nulls == 0:
                missing_summary = "There are no missing/null values."
            else:
                missing_columns = [
                    row["column_name"]
                    for row in rows
                    if row["null_count"] > 0
                ]

                missing_summary = (
                    f"There are {total_nulls:,} missing/null values "
                    f"across {len(missing_columns)} columns."
                )

            duplicate_summary = (
                "There are no duplicate rows."
                if duplicate_rows == 0
                else f"There are {duplicate_rows:,} duplicate rows."
            )

            answer = (
                f"Data quality summary:\n"
                f"• Rows: {total_rows:,}\n"
                f"• Columns: {total_columns:,}\n"
                f"• Overall completeness: {overall_completeness:.1f}%\n"
                f"• Missing/null values: {total_nulls:,}\n"
                f"• Duplicate rows: {duplicate_rows:,}\n\n"
                f"{missing_summary} {duplicate_summary}"
            )

            return {
                "question": question,
                "type": "data_quality",
                "answer": answer,
                "sql": (
                    "Data-quality profile generated using "
                    "DuckDB column-level null/distinct checks."
                ),
                "columns": [
                    "column_name",
                    "total_rows",
                    "null_count",
                    "distinct_count",
                    "completeness_pct",
                ],
                "rows": rows,
                "row_count": len(rows),
                "model": "local",
                "visualization": {
                    "type": "table",
                    "x": None,
                    "y": None,
                    "title": "Data Quality by Column",
                },
                "data_quality": {
                    "total_rows": total_rows,
                    "total_columns": total_columns,
                    "total_nulls": total_nulls,
                    "duplicate_rows": duplicate_rows,
                    "overall_completeness_pct": round(
                        overall_completeness,
                        1,
                    ),
                },
            }

        except Exception as error:
            print(
                "Data quality analysis error:",
                repr(error),
            )
            return None

    def _run_scenario(self, question: str):
        helper = getattr(self.llm, "_try_scenario_query", None)

        if helper:
            return helper(self.dataset, question)

        match = re.search(
            r"(increase|decrease|raise|reduce|grow|drop)\D{0,20}"
            r"(\d+(?:\.\d+)?)\s*%",
            question.lower(),
        )

        if not match:
            return None

        metric = self._metric_column(question)

        if not metric:
            return None

        pct = float(match.group(2)) / 100.0
        direction = match.group(1)
        factor = (
            1 + pct
            if direction in {"increase", "raise", "grow"}
            else 1 - pct
        )

        try:
            row = self.dataset.con.execute(
                f'SELECT SUM(TRY_CAST("{metric}" AS DOUBLE)) '
                "FROM main_table"
            ).fetchone()

            current = row[0]

            if current is None:
                return None

            projected = float(current) * factor
            verb = "increase" if factor >= 1 else "decrease"

            return {
                "question": question,
                "type": "scenario",
                "answer": (
                    f"Current total {metric.replace('_', ' ')} is "
                    f"{current:,.2f}. With a {abs(pct) * 100:g}% "
                    f"{verb}, the projected total is "
                    f"{projected:,.2f}."
                ),
                "sql": (
                    f'SELECT SUM(TRY_CAST("{metric}" AS DOUBLE)) '
                    "AS current_total FROM main_table"
                ),
                "columns": ["current_total"],
                "rows": [{"current_total": current}],
                "row_count": 1,
                "model": "local",
                "visualization": None,
            }

        except Exception:
            return None

    def _metric_column(self, question: str) -> str | None:
        columns = [str(c) for c in getattr(self.dataset, "columns", [])]
        q = question.lower()

        aliases = {
            "revenue": [
                "revenue", "sales", "sale", "income", "earnings",
            ],
            "units_sold": [
                "units sold", "units", "quantity", "qty",
            ],
            "unit_price": ["unit price", "price"],
            "marketing_spend": ["marketing spend", "marketing"],
            "customer_rating": ["rating", "customer rating"],
            "returns": ["returns", "return"],
        }

        for column in columns:
            if column.lower() in q:
                return column

        for canonical, names in aliases.items():
            for name in names:
                if name in q and canonical in columns:
                    return canonical


        return None
