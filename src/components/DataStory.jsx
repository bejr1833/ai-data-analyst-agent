import React from "react";

/* ==========================================================
   NUMBER FORMATTER
   ========================================================== */

function formatNumber(value) {
  if (
    value === null ||
    value === undefined ||
    value === ""
  ) {
    return "N/A";
  }

  const number = Number(value);

  if (Number.isNaN(number)) {
    return String(value);
  }

  return new Intl.NumberFormat("en-IN", {
    maximumFractionDigits: 2,
  }).format(number);
}


/* ==========================================================
   PERCENTAGE FORMATTER
   ========================================================== */

function formatPercentage(value) {
  const number = Number(value);

  if (Number.isNaN(number)) {
    return "N/A";
  }

  return `${number.toFixed(1)}%`;
}


/* ==========================================================
   CORRELATION INTERPRETATION
   ========================================================== */

function getCorrelationDescription(value) {
  const correlation = Number(value);

  if (Number.isNaN(correlation)) {
    return "The correlation could not be interpreted.";
  }

  const absoluteValue = Math.abs(correlation);

  let strength;

  if (absoluteValue >= 0.9) {
    strength = "very strong";
  } else if (absoluteValue >= 0.7) {
    strength = "strong";
  } else if (absoluteValue >= 0.5) {
    strength = "moderate";
  } else if (absoluteValue >= 0.3) {
    strength = "weak";
  } else {
    strength = "very weak";
  }

  const direction =
    correlation > 0
      ? "positive"
      : correlation < 0
      ? "negative"
      : "no";

  if (correlation === 0) {
    return "There is essentially no linear relationship between the two variables.";
  }

  return `The dataset shows a ${strength} ${direction} linear relationship between the variables.`;
}


/* ==========================================================
   GROUPED ANALYSIS STORY
   ========================================================== */
function buildAnomalyStory(rows, answer) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return (
      answer ||
      "No strong anomalies were detected in the dataset."
    );
  }

  const highest = rows[0];

  const value = Number(highest.value);
  const zScore = Number(highest.z_score);

  if (
    Number.isNaN(value) ||
    Number.isNaN(zScore)
  ) {
    return answer;
  }

  return (
    `${rows.length} potential anomaly${
      rows.length === 1 ? "" : "ies"
    } were detected. ` +
    `The most unusual value is ` +
    `${value.toLocaleString("en-IN", {
      maximumFractionDigits: 2,
    })}, with a z-score of ` +
    `${zScore.toFixed(2)}. ` +
    `These values should be reviewed in context ` +
    `before being treated as errors.`
  );
}


function buildGroupedStory(rows, visualization) {
  if (
    !Array.isArray(rows) ||
    rows.length === 0 ||
    !visualization
  ) {
    return null;
  }

  const x = visualization.x;
  const y = visualization.y;

  if (!x || !y) {
    return null;
  }

  const values = rows
    .map((row) => ({
      category: row[x],
      value: Number(row[y]),
    }))
    .filter(
      (item) =>
        item.category !== undefined &&
        !Number.isNaN(item.value)
    );

  if (values.length === 0) {
    return null;
  }

  const sorted = [...values].sort(
    (a, b) => b.value - a.value
  );

  const highest = sorted[0];
  const lowest = sorted[sorted.length - 1];

  const total = values.reduce(
    (sum, item) => sum + item.value,
    0
  );

  const highestShare =
    total !== 0
      ? (highest.value / total) * 100
      : 0;

  if (values.length === 1) {
    return (
      `The ${y} value for ${highest.category} ` +
      `is ${formatNumber(highest.value)}.`
    );
  }

  return (
    `${highest.category} has the highest ${y} at ` +
    `${formatNumber(highest.value)}, while ` +
    `${lowest.category} has the lowest at ` +
    `${formatNumber(lowest.value)}. ` +
    `${highest.category} contributes approximately ` +
    `${formatPercentage(highestShare)} of the total ${y}.`
  );
}


/* ==========================================================
   NUMERIC ANALYSIS STORY
   ========================================================== */

function buildNumericStory(rows, answer) {
  if (
    !Array.isArray(rows) ||
    rows.length === 0
  ) {
    return answer || null;
  }

  const firstRow = rows[0];

  if (!firstRow) {
    return answer || null;
  }

  const columns = Object.keys(firstRow);

  if (columns.length === 0) {
    return answer || null;
  }

  const column = columns[0];

  const value = firstRow[column];

  return (
    answer ||
    `The calculated ${column} is ${formatNumber(value)}.`
  );
}


/* ==========================================================
   STATISTICAL STORY
   ========================================================== */

function buildStatisticalStory(rows, answer) {
  if (
    !Array.isArray(rows) ||
    rows.length === 0
  ) {
    return answer || null;
  }

  const firstRow = rows[0];

  if (!firstRow) {
    return answer || null;
  }

  /* --------------------------------------------------------
     Correlation
     -------------------------------------------------------- */

  if (
    Object.prototype.hasOwnProperty.call(
      firstRow,
      "correlation"
    )
  ) {
    const correlation =
      Number(firstRow.correlation);

    return (
      `The correlation is ${correlation.toFixed(4)}. ` +
      getCorrelationDescription(correlation) +
      ` Correlation describes association, not causation.`
    );
  }

  /* --------------------------------------------------------
     Other statistics
     -------------------------------------------------------- */

  const columns = Object.keys(firstRow);

  if (columns.length === 0) {
    return answer || null;
  }

  const column = columns[0];

  return (
    answer ||
    `The calculated ${column} is ${formatNumber(
      firstRow[column]
    )}.`
  );
}


/* ==========================================================
   TREND STORY
   ========================================================== */

function buildTrendStory(rows, visualization) {
  if (
    !Array.isArray(rows) ||
    rows.length < 2 ||
    !visualization
  ) {
    return null;
  }

  const y = visualization.y;

  if (!y) {
    return null;
  }

  const values = rows
    .map((row) => Number(row[y]))
    .filter((value) => !Number.isNaN(value));

  if (values.length < 2) {
    return null;
  }

  const first = values[0];
  const last = values[values.length - 1];

  if (first === 0) {
    return (
      `The ${y} series changes from ` +
      `${formatNumber(first)} to ` +
      `${formatNumber(last)} over the observed period.`
    );
  }

  const percentageChange =
    ((last - first) / Math.abs(first)) * 100;

  let direction;

  if (percentageChange > 1) {
    direction = "increased";
  } else if (percentageChange < -1) {
    direction = "decreased";
  } else {
    direction = "remained relatively stable";
  }

  return (
    `${y} ${direction} from ` +
    `${formatNumber(first)} to ` +
    `${formatNumber(last)}, a change of approximately ` +
    `${formatPercentage(Math.abs(percentageChange))}.`
  );
}


/* ==========================================================
   MAIN DATA STORY COMPONENT
   ========================================================== */

export default function DataStory({
  result,
}) {
  if (!result) {
    return null;
  }

  const {
    type,
    answer,
    rows = [],
    visualization = null,
  } = result;

  let story = null;

  /* ========================================================
     GROUPED ANALYSIS
     ======================================================== */
  if (type === "anomaly_detection") {
  story = buildAnomalyStory(
    rows,
    answer
  );
}

  if (
    type === "grouped_analysis" ||
    (
      visualization &&
      visualization.type === "bar" &&
      rows.length > 1
    )
  ) {
    story = buildGroupedStory(
      rows,
      visualization
    );
  }


  /* ========================================================
     STATISTICAL ANALYSIS
     ======================================================== */

  else if (
    type === "statistical_analysis"
  ) {
    story = buildStatisticalStory(
      rows,
      answer
    );
  }


  /* ========================================================
     TREND ANALYSIS
     ======================================================== */

  else if (
    type === "trend_analysis"
  ) {
    story = buildTrendStory(
      rows,
      visualization
    );
  }


  /* ========================================================
     FORECAST
     ======================================================== */

  else if (
    type === "forecast"
  ) {
    story =
      answer ||
      "The forecast has been generated from the available historical data.";
  }


  /* ========================================================
     SCENARIO
     ======================================================== */

  else if (
    type === "scenario"
  ) {
    story =
      answer ||
      "The scenario analysis shows the projected impact of the requested change.";
  }


  /* ========================================================
     NUMERIC ANALYSIS
     ======================================================== */

  else if (
    type === "numeric_analysis"
  ) {
    story = buildNumericStory(
      rows,
      answer
    );
  }


  /* ========================================================
     BUSINESS INSIGHT
     ======================================================== */

  else if (
    type === "business_insight"
  ) {
    story =
      answer ||
      "The analysis identifies the most relevant business result from the dataset.";
  }


  /* ========================================================
     FALLBACK
     ======================================================== */

  else {
    story = answer || null;
  }


  /* ========================================================
     NOTHING TO DISPLAY
     ======================================================== */

  if (!story) {
    return null;
  }


  /* ========================================================
     UI
     ======================================================== */

  return (
    <div
      className="data-story"
      style={{
        marginTop: "18px",
        padding: "16px 18px",
        borderRadius: "12px",
        background: "#f8fafc",
        border: "1px solid #e2e8f0",
      }}
    >

      <div
        style={{
          fontSize: "15px",
          fontWeight: 700,
          marginBottom: "8px",
        }}
      >
        💡 Key Insight
      </div>

      <div
        style={{
          fontSize: "14px",
          lineHeight: 1.6,
          color: "#334155",
        }}
      >
        {story}
      </div>

    </div>
  );
}