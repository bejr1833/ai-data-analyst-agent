import React from "react";

function fmt(n) {
  if (n === null || n === undefined) return "—";

  return typeof n === "number"
    ? n.toLocaleString("en-IN")
    : n;
}

const METRIC_CONFIG = [
  {
    key: "row_count",
    label: "Rows",
    icon: "▤",
    tone: "teal",
  },
  {
    key: "column_count",
    label: "Columns",
    icon: "▦",
    tone: "violet",
  },
  {
    key: "duplicate_rows",
    label: "Duplicate rows",
    icon: "⧉",
    tone: "blue",
  },
  {
    key: "missing_cells",
    label: "Missing cells",
    icon: "◌",
    tone: "green",
  },
  {
    key: "numeric_column_count",
    label: "Numeric columns",
    icon: "#",
    tone: "amber",
  },
  {
    key: "categorical_column_count",
    label: "Categorical columns",
    icon: "Aa",
    tone: "purple",
  },
  {
    key: "datetime_column_count",
    label: "Datetime columns",
    icon: "◷",
    tone: "rose",
  },
];

function getMetricValue(item, overview) {
  switch (item.key) {
    case "row_count":
      return fmt(overview.row_count);

    case "column_count":
      return fmt(overview.column_count);

    case "duplicate_rows":
      return fmt(overview.duplicate_rows);

    case "missing_cells":
      return `${fmt(overview.total_missing_cells)} (${overview.missing_cell_pct ?? 0}%)`;

    case "numeric_column_count":
      return fmt(overview.numeric_column_count);

    case "categorical_column_count":
      return fmt(overview.categorical_column_count);

    case "datetime_column_count":
      return fmt(overview.datetime_column_count);

    default:
      return "—";
  }
}

export default function MetricsGrid({ overview }) {
  if (!overview) return null;

  return (
    <section className="metrics-section">
      <div className="metrics-section-header">
        <div>
          <div className="metrics-eyebrow">DATASET OVERVIEW</div>
          <h2 className="metrics-title">Dataset profile</h2>
        </div>

        <div className="metrics-status">
          <span className="metrics-status-dot" />
          Profile ready
        </div>
      </div>

      <div className="metrics-grid">
        {METRIC_CONFIG.map((item) => (
          <div
            className={`metric-cell metric-cell-${item.tone}`}
            key={item.key}
          >
            <div className="metric-icon" aria-hidden="true">
              {item.icon}
            </div>

            <div className="metric-content">
              <div className="metric-value">
                {getMetricValue(item, overview)}
              </div>

              <div className="metric-label">
                {item.label}
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}


