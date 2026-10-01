
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
    """Dataset-independent planner/executor/validator around the analysis engines."""

    def __init__(self, dataset):
        from app.services import llm_analyst

        self.dataset = dataset
        self.llm = llm_analyst

        self.tools: dict[str, Callable | None] = {
            "local_query": getattr(llm_analyst, "_try_local_query", None),
            "comparison": getattr(
                llm_analyst, "_try_comparison_query", None
            ),
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
            "filtering": getattr(
                llm_analyst, "_try_filtering_query", None
            ),
            "percentage_analysis": getattr(
                llm_analyst, "_try_percentage_query", None
            ),
            "anomaly_detection": getattr(
                llm_analyst, "_try_anomaly_query", None
            ),
            "data_quality": self._run_data_quality,
            "contextual_followup": getattr(
                llm_analyst, "_try_contextual_followup", None
            ),
        }

    def plan(self, question: str) -> list[AgentStep]:
        """
        Build a dataset-independent analysis plan.

        Routing principle:
        - Prefer deterministic local engines for common analytical intents.
        - Treat ranking as an analytical operation, never as a business-specific
          operation.
        - Keep grouped_analysis ahead of numeric_analysis when a dimension is
          explicitly requested.
        - Leave unsupported/ambiguous questions to the general LLM fallback.
        """
        q = (question or "").lower().strip()

        # 1. Conversational follow-ups have the highest priority.
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
            return [
                AgentStep(
                    "contextual_followup",
                    "Explain the previous analysis using conversation context",
                )
            ]

        # 2. Explicit multi-column comparisons.
        #
        # Examples:
        #   "Compare Mathematics and Programming"
        #   "Which has the higher average, Mathematics or Programming?"
        #   "Which has the lower average, Mathematics or Programming?"
        #   "What is the difference between Mathematics and Programming?"
        #
        # Comparison is routed separately from grouped analysis.
        # This prevents questions comparing numeric columns from
        # being interpreted as categorical/group comparisons.
        comparison_language = self._contains_any(
            q,
            [
                "compare",
                "comparison",
                " versus ",
                " vs ",
                "difference between",
                "difference of",
                "which has",
                "which is higher",
                "which is lower",
                "higher",
                "lower",
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
            ],
        )

        if comparison_language:
            columns = getattr(self.dataset, "columns", None)

            if columns is None:
                try:
                    columns = list(self.dataset.df.columns)
                except Exception:
                    columns = []

            numeric_columns = []

            try:
                from app.services.llm_analyst import _numeric_columns

                numeric_columns = _numeric_columns(self.dataset)
            except Exception:
                numeric_columns = []

            try:
                from app.services.llm_analyst import _find_mentioned_columns

                mentioned_columns = _find_mentioned_columns(
                    q,
                    columns,
                )
            except Exception:
                mentioned_columns = []

            mentioned_numeric = [
                column
                for column in mentioned_columns
                if column in numeric_columns
            ]

            if len(mentioned_numeric) >= 2:
                return [
                    AgentStep(
                        "comparison",
                        "Compare the explicitly requested numeric columns",
                    )
                ]

        # 3. Scenario / what-if analysis.

        # 3. Scenario / what-if analysis.
        if self._contains_any(
            q,
            [
                "what if",
                "suppose",
                "scenario",
                "impact if",
                "effect if",
                "increase by",
                "decrease by",
                "raise by",
                "reduce by",
                "grow by",
                "drop by",
            ],
        ):
            return [AgentStep("scenario", "Run scenario/what-if analysis")]

        # 4. Forecasting.
        if self._contains_any(
            q,
            [
                "forecast",
                "predict",
                "prediction",
                "future",
                "next week",
                "next month",
                "next quarter",
                "next year",
            ],
        ):
            return [AgentStep("forecast", "Forecast a future metric")]

        # 5. Anomaly / outlier detection.
        if self._contains_any(
            q,
            [
                "anomaly",
                "anomalies",
                "outlier",
                "outliers",
                "unusual",
                "abnormal",
                "unexpected",
                "irregular",
            ],
        ):
            return [
                AgentStep(
                    "anomaly_detection",
                    "Detect unusual observations",
                )
            ]

        # 6. Data quality.
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
                "unique values",
                "most unique",
                "distinct values",
                "most distinct",
                "highest distinct",
                "data completeness",
            ],
        ):
            return [
                AgentStep(
                    "data_quality",
                    "Profile completeness, nulls, duplicates, and distinct values",
                )
            ]

        # 7. Statistics / correlation / distribution.
        if self._contains_any(
            q,
            [
                "correlation",
                "correlate",
                "median",
                "standard deviation",
                "std dev",
                "variance",
                "percentile",
                "quartile",
                "distribution",
                "statistics",
                "statistical",
            ],
        ):
            return [AgentStep("statistics", "Run statistical analysis")]

        # 8. Time/trend analysis.
        if self._contains_any(
            q,
            [
                "trend",
                "over time",
                "time series",
                "historical trend",
                "growth over time",
                "monthly trend",
                "daily trend",
                "weekly trend",
                "yearly trend",
            ],
        ):
            return [AgentStep("trend", "Analyze the metric over time")]

        # ============================================================
        # HIGH-PRIORITY GENERIC ANALYSIS INTENTS
        # ============================================================
        #
        # Resolve concrete dataset-column operations before semantic
        # keyword operations such as "percentage" or "maximum".
        #
        # Examples:
        #   "average Percentage"
        #       -> AVG(Percentage)
        #
        #   "maximum Percentage"
        #       -> MAX(Percentage)
        #
        #   "total Total_Marks"
        #       -> SUM(Total_Marks)
        #
        #   "Percentage greater than 80"
        #       -> filtering
        #
        # A column named "Percentage" must NOT automatically mean
        # percentage/share analysis.
        # ============================================================

        columns = getattr(self.dataset, "columns", None)

        if columns is None:
            try:
                columns = list(self.dataset.df.columns)
            except Exception:
                columns = []

        normalized_columns = {
            str(column).strip().lower().replace("_", " "): column
            for column in columns
        }

        def mentioned_columns():
            found = []

            for normalized, original in normalized_columns.items():
                if normalized and normalized in q:
                    found.append(original)

            # Also support compact forms such as:
            # Attendance_Percent -> attendance percent
            # Total_Marks -> total marks
            #
            # Avoid duplicate matches.
            unique = []

            for column in found:
                if column not in unique:
                    unique.append(column)

            return unique

        mentioned = mentioned_columns()

        # ------------------------------------------------------------
        # Filtering / conditions
        # ------------------------------------------------------------
        #
        # Examples:
        #   Percentage greater than 80
        #   Attendance_Percent > 75
        #   Percentage > 80 and Attendance_Percent > 75
        #
        # These must be handled before percentage_analysis.
        # ------------------------------------------------------------

        comparison_pattern = re.compile(
            r"(?:>=|<=|!=|<>|>|<|=)|"
            r"\b(?:greater than|less than|at least|at most|equal to|"
            r"above|below|over|under)\b",
            re.IGNORECASE,
        )

        if mentioned and comparison_pattern.search(q):
            return [
                AgentStep(
                    "filtering",
                    "Filter dataset rows using one or more column conditions",
                )
            ]

        # ------------------------------------------------------------
        # Ranking / TOP-N / BOTTOM-N
        # ------------------------------------------------------------
        #
        # Ranking must be evaluated BEFORE generic aggregation because
        # questions such as:
        #
        #   "top 3 Departments by average Percentage"
        #
        # contain both ranking language and aggregation language.
        #
        # The semantic operation is:
        #
        #   GROUP BY Department
        #   AVG(Percentage)
        #   ORDER BY value DESC
        #   LIMIT 3
        # ------------------------------------------------------------

        ranking_pattern = re.compile(
            r"\b(?:top|bottom)\s+\d+\b",
            re.IGNORECASE,
        )

        # A standalone MAX/MIN question is numeric aggregation:
        #
        #   "What is the maximum Percentage?"
        #   "What is the minimum Percentage?"
        #
        # It becomes ranking only when there is a group/dimension
        # involved or explicit TOP/BOTTOM/ranking language.
        grouped_ranking_hint = (
            " by " in q
            or " for each " in q
            or " per " in q
            or " across " in q
            or " grouped " in q
            or " wise" in q
            or "wise" in q
            or "-wise" in q
            or "which " in q
            or "what department" in q
            or "what category" in q
            or "what group" in q
        )

        ranking_language = self._contains_any(
            q,
            [
                "highest",
                "lowest",
                "best",
                "worst",
                "most",
                "least",
                "leading",
                "largest",
                "smallest",
                "ranked",
                "ranking",
                "rank",
            ],
        )

        explicit_top_bottom = bool(ranking_pattern.search(q))

        # ------------------------------------------------------------
        # Scalar MAX/MIN questions
        # ------------------------------------------------------------
        # Questions such as:
        #   "What is the highest revenue?"
        #   "What is the lowest unit price?"
        #   "What is the maximum profit?"
        #
        # ask for ONE numeric value, not a ranked/grouped dimension.
        # Route these to numeric_analysis so the analysis engine can
        # resolve the metric dynamically and execute MAX/MIN.
        #
        # By contrast:
        #   "Which region has the highest revenue?"
        #   "Top 10 products by revenue"
        #
        # contain an explicit dimension/ranking request and remain
        # grouped/ranking operations.
        # ------------------------------------------------------------
        scalar_ranking_request = (
            ranking_language
            and not grouped_ranking_hint
            and len(mentioned) == 1
        )

        if scalar_ranking_request:
            return [
                AgentStep(
                    "numeric_analysis",
                    "Compute the highest or lowest value of the requested numeric column",
                )
            ]

        if explicit_top_bottom or (
            ranking_language and grouped_ranking_hint
        ):
            return [
                AgentStep(
                    "grouped_analysis",
                    "Rank groups using the requested metric and aggregation",
                )
            ]

        # ------------------------------------------------------------
        # Generic grouped aggregation
        # ------------------------------------------------------------
        #
        # IMPORTANT:
        # Grouped aggregation must be evaluated BEFORE the generic
        # numeric aggregation blocks below.
        #
        # Examples:
        #   "average Percentage by Department"
        #   "average Sales per Region"
        #   "total Revenue by Category"
        #   "mean Score for each Class"
        #   "sum Amount across Product"
        #
        # The grouping dimension is resolved dynamically from the
        # dataset schema by the grouped-analysis engine.
        # ------------------------------------------------------------

        grouped_intent = (
            " by " in q
            or " wise" in q
            or "wise" in q
            or "-wise" in q
            or " for each " in q
            or " each " in q
            or " per " in q
            or " across " in q
            or " grouped " in q
            or q.endswith(" grouped")
            or (
                "compare" in q
                and " between " in q
                and " and " in q
            )
        )

        aggregation_words = (
            "average",
            "avg",
            "mean",
            "sum",
            "total",
            "maximum",
            "minimum",
            "highest",
            "lowest",
            "max",
            "min",
            "median",
        )

        has_aggregation = self._contains_any(
            q,
            aggregation_words,
        )

        aggregation_language = self._contains_any(
            q,
            [
                "average",
                "avg",
                "mean",
                "sum",
                "total",
                "count",
                "how many",
                "number of",
                "minimum",
                "maximum",
                "min",
                "max",
                "median",
            ],
        )

        if grouped_intent and aggregation_language:
            return [
                AgentStep(
                    "grouped_analysis",
                    "Aggregate the requested metric grouped by the requested dimension",
                )
            ]

        # ------------------------------------------------------------
        # Multi-column numeric aggregation
        # ------------------------------------------------------------
        #
        # Example:
        #   "What is the average of Mathematics, Programming,
        #    and Data_Science?"
        #
        # If multiple numeric dataset columns are explicitly mentioned
        # and the question asks for an aggregate, do NOT interpret one
        # of those columns as a grouping dimension.
        # ------------------------------------------------------------

        if has_aggregation and len(mentioned) >= 2:
            return [
                AgentStep(
                    "numeric_analysis",
                    "Aggregate multiple explicitly requested numeric columns",
                )
            ]

        # ------------------------------------------------------------
        # Simple single-column aggregation
        # ------------------------------------------------------------
        #
        # Examples:
        #   "What is the average Percentage?"
        #   "What is the maximum Percentage?"
        #   "What is the minimum Percentage?"
        #   "What is the total Total_Marks?"
        #
        # ------------------------------------------------------------

        if has_aggregation and len(mentioned) == 1:
            return [
                AgentStep(
                    "numeric_analysis",
                    "Aggregate the explicitly requested dataset column",
                )
            ]

        # 9. Grouped analysis has priority over percentage/share detection.
        #
        # A column can legitimately be named "Percentage". For example:
        #   "average Percentage by Department"
        # means AVG(Percentage) grouped by Department, NOT percentage share.
        #
        # Likewise:
        #   "How many students are in each Department?"
        # means COUNT(*) grouped by Department.

        grouped_intent = (
            " by " in q
            or " wise" in q
            or "wise" in q
            or "-wise" in q
            or " for each " in q
            or " each " in q
            or " per " in q
            or " across " in q
            or " grouped " in q
            or q.endswith(" grouped")
            or (
                "compare" in q
                and " between " in q
                and " and " in q
            )
        )

        aggregation_language = self._contains_any(
            q,
            [
                "average",
                "avg",
                "mean",
                "sum",
                "total",
                "count",
                "how many",
                "number of",
                "minimum",
                "maximum",
                "min",
                "max",
                "median",
            ],
        )

        if grouped_intent and aggregation_language:
            return [
                AgentStep(
                    "grouped_analysis",
                    "Group and aggregate the requested metric by a dimension",
                )
            ]

        # 10. Percentage / rate questions.
        #
        # Only reach this block when the question is not already an
        # explicit grouped aggregation.
        percentage_intent = self._contains_any(
            q,
            [
                "percentage",
                "percent",
                "proportion",
                "share of",
                "rate",
                "ratio",
                "return rate",
            ],
        )

        ranking_language = self._contains_any(
            q,
            [
                "highest",
                "lowest",
                "best",
                "worst",
                "most",
                "least",
                "maximum",
                "minimum",
                "leading",
                "largest",
                "smallest",
                "ranked",
                "ranking",
                "rank",
            ],
        )

        if percentage_intent and not ranking_language:
            return [
                AgentStep(
                    "percentage_analysis",
                    "Calculate a percentage, proportion, rate, or ratio locally",
                )
            ]

        # 10. Explicit insight requests.
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
            return [
                AgentStep(
                    "main_insight",
                    "Identify the most important pattern in the dataset",
                )
            ]

        # 11. Ranking is generic analytics.
        #
        # IMPORTANT: Never route ranking to "business_insight". A question
        # such as "Which department has the highest average CGPA?" is the same
        # analytical operation as "Which category has the highest average
        # price?" or "Which region has the lowest mean score?".
        ranking_intent = (
            bool(re.search(r"\btop\s+\d+\b", q))
            or bool(re.search(r"\bbottom\s+\d+\b", q))
            or self._contains_any(
                q,
                [
                    "highest",
                    "lowest",
                    "best",
                    "worst",
                    "most",
                    "least",
                    "maximum",
                    "minimum",
                    "leading",
                    "largest",
                    "smallest",
                    "ranked",
                    "ranking",
                    "rank",
                ],
            )
        )

        # If ranking and an explicit grouping dimension are both present,
        # grouped_analysis is the correct deterministic engine.
        if ranking_intent:
            return [
                AgentStep(
                    "grouped_analysis",
                    "Rank groups using the requested metric and aggregation",
                )
            ]

        # 12. Grouped analysis.
        #
        # Examples:
        #   "average CGPA by Department"
        #   "how many students are in each Department"
        #   "sales per region"
        #   "mean score for each category"
        grouped_intent = (
            " by " in q
            or " wise" in q
            or "wise" in q
            or "-wise" in q
            or " for each " in q
            or " per " in q
            or " across " in q
            or " grouped " in q
            or q.endswith(" grouped")
            or (
                "compare" in q
                and " between " in q
                and " and " in q
            )
        )

        if grouped_intent:
            return [
                AgentStep(
                    "grouped_analysis",
                    "Group a metric by a requested dimension",
                )
            ]

        # 13. Generic scalar aggregation/count.
        if self._contains_any(
            q,
            [
                "total",
                "sum",
                "average",
                "avg",
                "mean",
                "count",
                "how many",
                "maximum",
                "minimum",
            ],
        ):
            return [
                AgentStep(
                    "numeric_analysis",
                    "Compute a numeric metric locally",
                )
            ]

        # 14. Final deterministic attempt. If it cannot understand the
        # question, run() falls through to the general LLM analysis engine.
        return [
            AgentStep(
                "local_query",
                "Try a deterministic local dataset query first",
            )
        ]

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
        fallback_used = False

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
                "explain the difference",
                "explain the main difference",
                "difference in these results",
                "difference between these results",
                "differences in these results",
                "differences between these results",
                "compare these results",
                "compare the results",
                "comparison of these results",
                "main difference",
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
            fallback_used = True
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
            "fallback_used": fallback_used,
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
        """Return True when any phrase/word is present without substring traps."""
        normalized = f" {str(text).lower().strip()} "
        for word in words:
            candidate = str(word).lower().strip()
            if not candidate:
                continue
            if " " in candidate or "-" in candidate:
                if candidate in normalized:
                    return True
            else:
                if re.search(rf"\b{re.escape(candidate)}\b", normalized):
                    return True
        return False

    def _run_data_quality(self, dataset, question: str):
        """
        Deterministic data-quality analysis.

        Supports:
        - Full quality summary
        - Missing/null column analysis
        - Distinct/unique value analysis
        - Duplicate row analysis
        - Completeness analysis
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
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'main_table'
                ORDER BY ordinal_position
                """
            ).fetchall()

            column_names = [
                str(row[0])
                for row in columns_result
            ]

            column_types = {
                str(row[0]): str(row[1])
                for row in columns_result
            }

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

                missing_pct = (
                    0.0
                    if column_total == 0
                    else (
                        null_count / column_total
                    ) * 100.0
                )

                distinct_pct = (
                    0.0
                    if column_total == 0
                    else (
                        distinct_count / column_total
                    ) * 100.0
                )

                if column_total > 0 and null_count == column_total:
                    quality_status = "Critical"
                elif missing_pct >= 20.0:
                    quality_status = "Needs attention"
                elif missing_pct > 0:
                    quality_status = "Review"
                else:
                    quality_status = "Good"

                rows.append(
                    {
                        "column_name": column,
                        "data_type": column_types.get(
                            column,
                            "UNKNOWN",
                        ),
                        "total_rows": column_total,
                        "null_count": null_count,
                        "missing_pct": round(
                            missing_pct,
                            1,
                        ),
                        "distinct_count": distinct_count,
                        "distinct_pct": round(
                            distinct_pct,
                            1,
                        ),
                        "completeness_pct": round(
                            completeness,
                            1,
                        ),
                        "quality_status": quality_status,
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

            q = str(question).lower().strip()

            response_rows = rows

            if "missing" in q or "null" in q:
                response_rows = [
                    row
                    for row in rows
                    if row["null_count"] > 0
                ]

                if not response_rows:
                    answer = (
                        "No columns contain missing/null values. "
                        "All columns are 100% complete."
                    )
                else:
                    missing_summary = [
                        (
                            f"{row['column_name']}: "
                            f"{row['null_count']:,} missing "
                            f"({row['missing_pct']:.1f}%)"
                        )
                        for row in response_rows
                    ]

                    answer = (
                        "Columns with missing/null values: "
                        + ", ".join(missing_summary)
                        + "."
                    )

            elif "unique" in q or "distinct" in q:
                response_rows = sorted(
                    rows,
                    key=lambda row: row["distinct_count"],
                    reverse=True,
                )[:5]

                unique_summary = [
                    (
                        f"{row['column_name']}: "
                        f"{row['distinct_count']:,} distinct values "
                        f"({row['distinct_pct']:.1f}% of rows)"
                    )
                    for row in response_rows
                ]

                answer = (
                    "Columns with the most unique/distinct values: "
                    + ", ".join(unique_summary)
                    + "."
                )

            elif "duplicate" in q:
                response_rows = []

                if duplicate_rows == 0:
                    answer = (
                        "There are no duplicate rows in the dataset."
                    )
                else:
                    answer = (
                        f"The dataset contains "
                        f"{duplicate_rows:,} duplicate rows."
                    )

            elif (
                "completeness" in q
                or "complete" in q
            ):
                answer = (
                    f"Overall data completeness is "
                    f"{overall_completeness:.1f}%. "
                    f"There are {total_nulls:,} missing/null values "
                    f"across {total_columns:,} columns."
                )

            else:
                attention_columns = [
                    row
                    for row in rows
                    if row["quality_status"] != "Good"
                ]

                if not attention_columns:
                    quality_detail = (
                        "All columns passed the quality checks."
                    )
                else:
                    attention_summary = [
                        (
                            f"{row['column_name']} "
                            f"({row['missing_pct']:.1f}% missing, "
                            f"status: {row['quality_status']})"
                        )
                        for row in attention_columns
                    ]

                    quality_detail = (
                        "Columns needing attention: "
                        + ", ".join(attention_summary)
                        + "."
                    )

                answer = (
                    f"Data quality summary:\n"
                    f"- Rows: {total_rows:,}\n"
                    f"- Columns: {total_columns:,}\n"
                    f"- Overall completeness: "
                    f"{overall_completeness:.1f}%\n"
                    f"- Missing/null values: {total_nulls:,}\n"
                    f"- Duplicate rows: {duplicate_rows:,}\n\n"
                    f"{quality_detail}"
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
                    "data_type",
                    "total_rows",
                    "null_count",
                    "missing_pct",
                    "distinct_count",
                    "distinct_pct",
                    "completeness_pct",
                    "quality_status",
                ],
                "rows": response_rows,
                "row_count": len(response_rows),
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
        q = question.lower().strip()

        aliases = {
            "revenue": [
                "total revenue",
                "revenue",
                "total sales",
                "sales",
                "sale",
                "income",
                "earnings",
            ],
            "units_sold": [
                "units sold",
                "units_sold",
                "quantity",
                "qty",
                "units",
            ],
            "unit_price": [
                "unit price",
                "unit_price",
                "average price",
                "price per unit",
                "price",
            ],
            "marketing_spend": [
                "marketing spend",
                "marketing_spend",
                "marketing",
            ],
            "customer_rating": [
                "customer rating",
                "customer_rating",
                "rating",
            ],
            "returns": [
                "returns",
                "return",
            ],
        }

        # 1. Exact dataset column names first.
        # Sort by length so more specific names win.
        for column in sorted(columns, key=len, reverse=True):
            column_lower = column.lower()
            if column_lower in q:
                return column

        # 2. Match the longest alias first.
        # This prevents generic words such as "price" or "units"
        # from overriding more specific phrases.
        alias_matches = []

        for canonical, names in aliases.items():
            if canonical not in columns:
                continue

            for name in names:
                if name in q:
                    alias_matches.append((len(name), canonical))

        if alias_matches:
            alias_matches.sort(reverse=True)
            return alias_matches[0][1]

        return None














