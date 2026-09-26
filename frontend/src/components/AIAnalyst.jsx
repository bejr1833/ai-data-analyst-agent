import { useEffect, useMemo, useState } from "react";
import { askDataset } from "../api/client.js";
import AnalysisChart from "./AnalysisChart";
import DataStory from "./DataStory";
import AgentTrace from "./AgentTrace";

const BASE_SUGGESTIONS = [
  "What is the total revenue?",
  "Show total revenue by region",
  "Which region has the highest revenue?",
  "Show revenue trend over time",
  "Forecast revenue for the next 7 days",
  "What is the correlation between revenue and marketing spend?",
  "What if revenue increases by 20%?",
  "Show me the data quality summary",
];

function extractRows(result) {
  if (Array.isArray(result?.rows)) return result.rows;
  if (Array.isArray(result?.data?.rows)) return result.data.rows;
  if (Array.isArray(result?.analysis?.rows)) return result.analysis.rows;
  return [];
}

function extractVisualization(result) {
  const candidates = [
    result?.visualization,
    result?.data?.visualization,
    result?.analysis?.visualization,
  ];

  return candidates.find(
    (value) => value && typeof value === "object"
  ) || null;
}

function isValidVisualization(visualization) {
  if (!visualization || typeof visualization !== "object") return false;

  const { x, y, type } = visualization;

  return (
    Boolean(x) &&
    Boolean(y) &&
    ["bar", "line", "scatter", "forecast"].includes(type)
  );
}

function hasUsableChart(message) {
  if (
    message?.role !== "assistant" ||
    !Array.isArray(message?.rows) ||
    message.rows.length === 0 ||
    !isValidVisualization(message?.visualization)
  ) {
    return false;
  }

  const { type, x, y, forecastY = "forecast" } =
    message.visualization;

  if (type !== "forecast") {
    return message.rows.some((row) => {
      if (!row || typeof row !== "object") return false;
      return (
        Object.prototype.hasOwnProperty.call(row, x) &&
        Object.prototype.hasOwnProperty.call(row, y)
      );
    });
  }

  return message.rows.some((row) => {
    if (!row || typeof row !== "object") return false;

    const hasX = Object.prototype.hasOwnProperty.call(row, x);
    const hasY = Object.prototype.hasOwnProperty.call(row, y);
    const hasForecast = Object.prototype.hasOwnProperty.call(
      row,
      forecastY
    );

    return hasX && (hasY || hasForecast);
  });
}

function isDataQualityQuestion(message) {
  const question = String(
    message?.question || message?.userQuestion || ""
  ).toLowerCase();

  const answer = String(message?.text || "").toLowerCase();

  return (
    question.includes("data quality") ||
    question.includes("data-quality") ||
    question.includes("data quality summary") ||
    answer.includes("data quality summary")
  );
}

function isQualityRow(row) {
  if (!row || typeof row !== "object") return false;

  const keys = Object.keys(row).map((key) =>
    key.toLowerCase()
  );

  return (
    keys.includes("column_name") &&
    keys.includes("total_rows") &&
    keys.includes("null_count") &&
    keys.includes("distinct_count")
  );
}

function formatNumber(value) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }

  const number = Number(value);

  if (!Number.isFinite(number)) return String(value);

  return number.toLocaleString("en-IN");
}

function isMetricVisualization(visualization) {
  return (
    visualization &&
    typeof visualization === "object" &&
    visualization.type === "metric"
  );
}

function MetricCard({ rows, visualization, answer }) {
  const firstRow = rows?.[0];
  const keys = firstRow && typeof firstRow === "object"
    ? Object.keys(firstRow)
    : [];

  const preferredKey = keys.find((key) =>
    ["result", "value", "total", "count", "average", "sum", "revenue"]
      .includes(String(key).toLowerCase())
  );

  const value = preferredKey ? firstRow[preferredKey] : firstRow?.[keys[0]];
  const title = visualization?.title || "Analysis Result";

  return (
    <div
      className="ai-metric-card"
      style={{
        marginTop: 18,
        width: "100%",
        boxSizing: "border-box",
        padding: "22px 24px",
        borderRadius: 18,
        border: "1px solid rgba(102, 217, 168, 0.24)",
        background: "linear-gradient(145deg, rgba(20,45,55,.96), rgba(10,27,38,.96))",
      }}
    >
      <div
        style={{
          fontSize: 12,
          fontWeight: 800,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: "#9db3c9",
          marginBottom: 8,
        }}
      >
        {title}
      </div>
      <div
        style={{
          fontSize: 32,
          lineHeight: 1.15,
          fontWeight: 850,
          color: "#66d9a8",
          wordBreak: "break-word",
        }}
      >
        {formatNumber(value)}
      </div>
      {answer && (
        <div
          style={{
            marginTop: 10,
            color: "#c7d5e8",
            fontSize: 13,
            lineHeight: 1.55,
          }}
        >
          {answer}
        </div>
      )}
    </div>
  );
}

function DataQualityTable({ rows }) {
  const qualityRows = rows.filter(isQualityRow);

  if (!qualityRows.length) return null;

  return (
    <div
      className="ai-data-quality-card"
      style={{
        marginTop: 18,
        width: "100%",
        overflowX: "auto",
        border: "1px solid rgba(140, 175, 210, 0.20)",
        borderRadius: 16,
        background:
          "linear-gradient(145deg, rgba(18,31,52,.96), rgba(10,20,36,.96))",
        boxSizing: "border-box",
      }}
    >
      <div
        style={{
          padding: "16px 18px 10px",
          fontSize: 14,
          fontWeight: 800,
          color: "#f4f7ff",
        }}
      >
        Data Quality by Column
      </div>

      <div style={{ padding: "0 14px 14px" }}>
        <table
          style={{
            width: "100%",
            minWidth: 680,
            borderCollapse: "separate",
            borderSpacing: 0,
            color: "#eaf2ff",
            fontSize: 13,
          }}
        >
          <thead>
            <tr>
              {[
                "Column",
                "Rows",
                "Missing",
                "Distinct",
                "Completeness",
              ].map((heading) => (
                <th
                  key={heading}
                  style={{
                    textAlign: heading === "Column" ? "left" : "right",
                    padding: "11px 12px",
                    color: "#aebed4",
                    background: "rgba(255,255,255,.045)",
                    borderBottom:
                      "1px solid rgba(140,175,210,.18)",
                    fontWeight: 750,
                    whiteSpace: "nowrap",
                  }}
                >
                  {heading}
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {qualityRows.map((row, index) => {
              const total = Number(row.total_rows) || 0;
              const missing = Number(row.null_count) || 0;
              const completeness =
                total > 0
                  ? Math.max(
                      0,
                      Math.min(
                        100,
                        ((total - missing) / total) * 100
                      )
                    )
                  : 0;

              return (
                <tr key={`${row.column_name}-${index}`}>
                  <td
                    style={{
                      padding: "11px 12px",
                      borderBottom:
                        "1px solid rgba(140,175,210,.10)",
                      color: "#f4f7ff",
                      fontWeight: 650,
                      textAlign: "left",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {String(row.column_name)}
                  </td>

                  <td
                    style={{
                      padding: "11px 12px",
                      textAlign: "right",
                      borderBottom:
                        "1px solid rgba(140,175,210,.10)",
                    }}
                  >
                    {formatNumber(total)}
                  </td>

                  <td
                    style={{
                      padding: "11px 12px",
                      textAlign: "right",
                      borderBottom:
                        "1px solid rgba(140,175,210,.10)",
                      color:
                        missing === 0 ? "#66d9a8" : "#ff9a9a",
                      fontWeight: 750,
                    }}
                  >
                    {formatNumber(missing)}
                  </td>

                  <td
                    style={{
                      padding: "11px 12px",
                      textAlign: "right",
                      borderBottom:
                        "1px solid rgba(140,175,210,.10)",
                    }}
                  >
                    {formatNumber(row.distinct_count)}
                  </td>

                  <td
                    style={{
                      padding: "11px 12px",
                      textAlign: "right",
                      borderBottom:
                        "1px solid rgba(140,175,210,.10)",
                      color:
                        completeness === 100
                          ? "#66d9a8"
                          : "#f4c76b",
                      fontWeight: 800,
                    }}
                  >
                    {completeness.toFixed(1)}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function buildConversationHistory(messages) {
  return messages
    .filter(
      (message) =>
        message.role === "user" ||
        message.role === "assistant"
    )
    .map((message) => ({
      role: message.role,
      text: message.text || "",
      rows: Array.isArray(message.rows) ? message.rows : [],
      visualization:
        message.visualization &&
        typeof message.visualization === "object"
          ? message.visualization
          : null,
      sql: typeof message.sql === "string" ? message.sql : null,
      resultType:
        message.resultType || message.type || null,
      model: message.model || null,
      agent: message.agent || null,
    }));
}

function storageKey(datasetId) {
  return `ai-analyst-chat:${datasetId}`;
}

function safeParseMessages(value) {
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function downloadText(filename, content, type = "text/plain") {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");

  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function buildTextReport(messages) {
  const lines = [
    "AI DATA ANALYST REPORT",
    "======================",
    "",
  ];

  messages.forEach((message, index) => {
    if (
      message.role !== "user" &&
      message.role !== "assistant"
    ) {
      return;
    }

    lines.push(
      `${message.role === "user" ? "USER" : "AI"} ${index + 1}`
    );
    lines.push(message.text || "");
    lines.push("");

    if (
      message.role === "assistant" &&
      typeof message.sql === "string" &&
      message.sql.trim()
    ) {
      lines.push("SQL");
      lines.push("---");
      lines.push(message.sql.trim());
      lines.push("");
    }
  });

  return lines.join("\n");
}

function makeFollowUps(message) {
  if (!message?.text) return [];

  if (isDataQualityQuestion(message)) {
    return [
      "Which columns have missing values?",
      "Show me the columns with the most unique values",
    ];
  }

  const visualization = message.visualization;

  if (visualization?.type === "bar") {
    return [
      "Explain the main difference in these results",
      "Which category contributes the most?",
    ];
  }

  if (
    visualization?.type === "line" ||
    visualization?.type === "forecast"
  ) {
    return [
      "Explain the trend",
      "What should I watch next?",
    ];
  }

  if (message.rows?.length > 0) {
    return [
      "Explain these results",
      "What is the main insight?",
    ];
  }

  return [
    "Can you explain that?",
    "What is the main insight?",
  ];
}

export default function AIAnalyst({ datasetId }) {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [copiedIndex, setCopiedIndex] = useState(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setHydrated(false);

    if (!datasetId) {
      setMessages([]);
      setHydrated(true);
      return;
    }

    try {
      const saved = sessionStorage.getItem(
        storageKey(datasetId)
      );
      setMessages(saved ? safeParseMessages(saved) : []);
    } catch {
      setMessages([]);
    } finally {
      setHydrated(true);
    }
  }, [datasetId]);

  useEffect(() => {
    if (!datasetId || !hydrated) return;

    try {
      sessionStorage.setItem(
        storageKey(datasetId),
        JSON.stringify(messages)
      );
    } catch {
      // Storage is optional.
    }
  }, [datasetId, messages, hydrated]);

  async function handleAsk(event) {
    event.preventDefault();

    const trimmed = question.trim();

    if (!trimmed || loading || !datasetId) return;

    const conversationHistory =
      buildConversationHistory(messages);

    setMessages((previous) => [
      ...previous,
      { role: "user", text: trimmed },
    ]);

    setQuestion("");
    setLoading(true);

    try {
      const result = await askDataset(
        datasetId,
        trimmed,
        conversationHistory
      );

      const resultRows = extractRows(result);
      const resultVisualization =
        extractVisualization(result);

      console.log("AI Analyst chart payload:", {
        type: resultVisualization?.type || null,
        x: resultVisualization?.x || null,
        y: resultVisualization?.y || null,
        forecastY: resultVisualization?.forecastY || null,
        rowCount: resultRows.length,
        firstRow: resultRows[0] || null,
      });

      const assistantMessage = {
        role: "assistant",
        text:
          result?.answer ||
          "No answer was returned.",
        rows: resultRows,
        visualization: resultVisualization,
        sql:
          typeof result?.sql === "string"
            ? result.sql
            : null,
        resultType:
          result?.type ||
          result?.resultType ||
          null,
        model: result?.model || null,
        agent: result?.agent || null,
        question: trimmed,
        rowCount:
          typeof result?.row_count === "number"
            ? result.row_count
            : resultRows.length,
      };

      setMessages((previous) => [
        ...previous,
        assistantMessage,
      ]);
    } catch (error) {
      setMessages((previous) => [
        ...previous,
        {
          role: "error",
          text:
            error?.message ||
            "Unable to analyze the dataset.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function clearChat() {
    if (loading) return;

    setMessages([]);

    if (datasetId) {
      try {
        sessionStorage.removeItem(
          storageKey(datasetId)
        );
      } catch {
        // Ignore storage errors.
      }
    }
  }

  function useSuggestion(text) {
    if (!loading) setQuestion(text);
  }

  async function copyAnswer(message, index) {
    if (!message?.text) return;

    try {
      await navigator.clipboard.writeText(message.text);
      setCopiedIndex(index);
      window.setTimeout(
        () => setCopiedIndex(null),
        1400
      );
    } catch {
      // Clipboard permission is optional.
    }
  }

  function exportConversation() {
    if (!messages.length || loading) return;

    downloadText(
      "ai-data-analyst-report.txt",
      buildTextReport(messages)
    );
  }

  const followUps = useMemo(() => {
    const lastAssistant = [...messages]
      .reverse()
      .find(
        (message) => message.role === "assistant"
      );

    return makeFollowUps(lastAssistant);
  }, [messages]);

  return (
    <section
      className="ai-analyst"
      style={{
        overflow: "visible",
        height: "auto",
        maxHeight: "none",
      }}
    >
      <div className="ai-analyst-header">
        <div>
          <h2>AI Data Analyst</h2>
          <p>
            Ask questions about your uploaded dataset
            in natural language.
          </p>
        </div>

        <div className="ai-analyst-actions">
          <button
            type="button"
            className="ai-analyst-export"
            onClick={exportConversation}
            disabled={!messages.length || loading}
          >
            Export
          </button>

          <button
            type="button"
            onClick={clearChat}
            disabled={
              loading || messages.length === 0
            }
          >
            Clear
          </button>
        </div>
      </div>

      <div className="ai-analyst-suggestions">
        {BASE_SUGGESTIONS.map((suggestion) => (
          <button
            type="button"
            key={suggestion}
            onClick={() => useSuggestion(suggestion)}
            disabled={loading}
          >
            {suggestion}
          </button>
        ))}
      </div>

      <form
        onSubmit={handleAsk}
        className="ai-analyst-form"
      >
        <input
          value={question}
          onChange={(event) =>
            setQuestion(event.target.value)
          }
          placeholder="Ask something about your data..."
          disabled={loading}
          autoComplete="off"
        />

        <button
          type="submit"
          disabled={
            loading ||
            !question.trim() ||
            !datasetId
          }
        >
          {loading ? "Analyzing..." : "Ask"}
        </button>
      </form>

      <div
        className="ai-analyst-chat"
        style={{
          overflow: "visible",
          height: "auto",
          maxHeight: "none",
        }}
      >
        {messages.map((message, index) => {
          const qualityQuestion =
            message.role === "assistant" &&
            isDataQualityQuestion(message);

          const metricResult =
            message.role === "assistant" &&
            isMetricVisualization(message.visualization);

          return (
            <div
              key={`${message.role}-${index}`}
              className={`chat-message ${message.role}`}
              style={
                message.role === "assistant"
                  ? {
                      width: "100%",
                      maxWidth: "100%",
                      alignSelf: "stretch",
                      boxSizing: "border-box",
                      overflow: "visible",
                      height: "auto",
                      maxHeight: "none",
                    }
                  : undefined
              }
            >
              <div className="chat-message-text">
                {message.text}
              </div>

              {message.role === "assistant" && (
                <div className="assistant-message-actions">
                  <button
                    type="button"
                    onClick={() =>
                      copyAnswer(message, index)
                    }
                  >
                    {copiedIndex === index
                      ? "Copied"
                      : "Copy answer"}
                  </button>
                </div>
              )}

              {qualityQuestion ? (
                <DataQualityTable
                  rows={message.rows}
                />
              ) : metricResult ? (
                <MetricCard
                  rows={message.rows}
                  visualization={message.visualization}
                  answer={message.text}
                />
              ) : (
                hasUsableChart(message) && (
                  <div
                    style={{
                      width: "100%",
                      maxWidth: "100%",
                      minWidth: 0,
                      boxSizing: "border-box",
                      marginTop: 16,
                      overflow: "visible",
                    }}
                  >
                    <AnalysisChart
                      rows={message.rows}
                      visualization={
                        message.visualization
                      }
                    />
                  </div>
                )
              )}

              {message.role === "assistant" &&
                message.agent && (
                  <AgentTrace
                    agent={message.agent}
                    sql={message.sql}
                  />
                )}

              {message.role === "assistant" &&
                message.sql && (
                  <details className="sql-details">
                    <summary>SQL used</summary>
                    <pre>{message.sql}</pre>
                  </details>
                )}

              {message.role === "assistant" &&
                message.rows?.length > 0 &&
                !qualityQuestion &&
                !metricResult && (
                  <DataStory
                    rows={message.rows}
                    visualization={
                      message.visualization
                    }
                  />
                )}

              {qualityQuestion &&
                message.rows?.length > 0 && (
                  <div
                    style={{
                      marginTop: 16,
                      padding: "14px 16px",
                      borderRadius: 14,
                      border:
                        "1px solid rgba(102,217,168,.18)",
                      background:
                        "rgba(102,217,168,.055)",
                      color: "#bfead6",
                      fontSize: 13,
                      lineHeight: 1.65,
                    }}
                  >
                    <strong
                      style={{ color: "#66d9a8" }}
                    >
                      Data quality insight:
                    </strong>{" "}
                    Review the table above for missing,
                    distinct, and completeness values for
                    every column.
                  </div>
                )}

              {message.role === "assistant" &&
                index === messages.length - 1 &&
                followUps.length > 0 && (
                  <div className="ai-followups">
                    <span>Continue analysis</span>

                    <div>
                      {followUps.map((followUp) => (
                        <button
                          type="button"
                          key={followUp}
                          onClick={() =>
                            useSuggestion(followUp)
                          }
                          disabled={loading}
                        >
                          {followUp}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
            </div>
          );
        })}

        {loading && (
          <div className="chat-message assistant ai-loading-message">
            <span className="ai-loading-dot" />
            <span className="ai-loading-dot" />
            <span className="ai-loading-dot" />
            <span className="ai-loading-text">
              Analyzing your dataset...
            </span>
          </div>
        )}
      </div>
    </section>
  );
}
