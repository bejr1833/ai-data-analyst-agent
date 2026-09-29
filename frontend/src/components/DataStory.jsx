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

  return new Intl.NumberFormat("en-US", {
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

  return `${number.toFixed(2)}%`;
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
   ANOMALY STORY
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


/* ==========================================================
   GROUPED ANALYSIS STORY
   ========================================================== */

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
      category: row?.[x],
      value: Number(row?.[y]),
    }))
    .filter(
      (item) =>
        item.category !== undefined &&
        item.category !== null &&
        String(item.category).trim() !== "" &&
        Number.isFinite(item.value)
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

  /* ========================================================
     SINGLE CATEGORY
     ======================================================== */

  if (values.length === 1) {
    return (
      `The ${y} value for ${highest.category} is ` +
      `${formatNumber(highest.value)}.`
    );
  }


  /* ========================================================
     TWO-CATEGORY COMPARISON
     ======================================================== */

  if (values.length === 2) {
    const first = values[0];
    const second = values[1];

    const difference =
      Math.abs(first.value - second.value);

    if (difference === 0) {
      return (
        `${first.category} and ${second.category} have the same ` +
        `${y} value of ${formatNumber(first.value)}. ` +
        `Both contribute approximately 50.0% of the selected comparison total.`
      );
    }

    const higher =
      first.value >= second.value
        ? first
        : second;

    const lower =
      first.value >= second.value
        ? second
        : first;

    const percentageDifference =
      lower.value !== 0
        ? (difference / Math.abs(lower.value)) * 100
        : null;

    const higherShare =
      total !== 0
        ? (higher.value / total) * 100
        : 0;

    return (
      `${higher.category} generated ${formatNumber(difference)} more ` +
      `${y} than ${lower.category}. ` +
      `This represents a ` +
      `${
        percentageDifference !== null
          ? formatPercentage(percentageDifference)
          : "N/A"
      } difference relative to ${lower.category}. ` +
      `${higher.category} accounts for approximately ` +
      `${formatPercentage(higherShare)} of the selected comparison total.`
    );
  }


  /* ========================================================
     MULTI-CATEGORY GROUPED ANALYSIS
     ======================================================== */

  const spread =
    highest.value - lowest.value;

  const spreadPercentage =
    lowest.value !== 0
      ? (spread / Math.abs(lowest.value)) * 100
      : null;

  const highestShare =
    total !== 0
      ? (highest.value / total) * 100
      : 0;

  return (
    `${highest.category} has the highest ${y} at ` +
    `${formatNumber(highest.value)}, while ` +
    `${lowest.category} has the lowest at ` +
    `${formatNumber(lowest.value)}. ` +
    `The gap between the highest and lowest categories is ` +
    `${formatNumber(spread)}` +
    `${
      spreadPercentage !== null
        ? `, or approximately ${formatPercentage(spreadPercentage)} relative to the lowest category`
        : ""
    }. ` +
    `${highest.category} contributes approximately ` +
    `${formatPercentage(highestShare)} of the selected total.`
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

function cleanStoryText(value) {
  if (value == null) return "";

  let text = String(value);

  /*
   * Repair common UTF-8 / Windows-1252 mojibake.
   */

  text = text
    .replace(/\u00E2\u20AC\u201D/g, "-")
    .replace(/\u00E2\u20AC\u2013/g, "-")
    .replace(/\u00E2\u20AC\u00A6/g, "...")
    .replace(/\u00E2\u20AC\u201C/g, '"')
    .replace(/\u00E2\u20AC\u009D/g, '"')
    .replace(/\u00E2\u20AC\u2122/g, "'")
    .replace(/\u00E2\u20AC\u02DC/g, "'")
    .replace(/\u00C2\u00A0/g, " ")
    .replace(/\u00C2/g, "")
    .replace(/\u00EF\u00BF\u00BD/g, "")
    .replace(/\uFFFD/g, "");

  /*
   * Remove the specific corrupted marker visible in
   * the Key Insight text:
   *
   * AÃ¢â‚¬Â¦Ã¢â‚¬ South
   * AÃ¢â‚¬Â¦Ã¢â‚¬ Phone
   *
   * while preserving South / Phone and the rest of
   * the sentence.
   */

  text = text.replace(
    /\u0041\s*\u00E2\u20AC\u00A6\s*\u00E2\u20AC[^\p{L}\p{N}]*/gu,
    ""
  );

  /*
   * Clean remaining mojibake fragments if any remain.
   */

  text = text
    .replace(/[\u00E2\u00C3][\u201A\u20AC\u0080-\u009F][^\p{L}\p{N}\s]*/gu, "")
    .replace(/[\u00E2\u00C3][\u201A\u20AC\u0080-\u009F]/gu, "")
    .replace(/\u00E2[^\p{L}\p{N}\s]{1,8}/gu, "")
    .replace(/\u00E2\u0080[^\p{L}\p{N}]*/gu, "")
    .replace(/\u00C3[^\p{L}\p{N}]*/gu, "")
    .replace(/[ \t]{2,}/g, " ")
    .replace(/ +([,.;:!?])/g, "$1")
    .replace(/\n[ \t]+/g, "\n")
    .trim();

  return text;
}
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
     STORY SELECTION
     ======================================================== */

  if (type === "anomaly_detection") {
    story = buildAnomalyStory(
      rows,
      answer
    );
  } else if (
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
  } else if (
    type === "statistical_analysis"
  ) {
    story = buildStatisticalStory(
      rows,
      answer
    );
  } else if (
    type === "trend_analysis"
  ) {
    story = buildTrendStory(
      rows,
      visualization
    );
  } else if (
    type === "forecast"
  ) {
    story =
      answer ||
      "The forecast has been generated from the available historical data.";
  } else if (
    type === "scenario"
  ) {
    story =
      answer ||
      "The scenario analysis shows the projected impact of the requested change.";
  } else if (
    type === "numeric_analysis"
  ) {
    story = buildNumericStory(
      rows,
      answer
    );
  } else if (
    type === "business_insight"
  ) {
    story =
      answer ||
      "The analysis identifies the most relevant business result from the dataset.";
  } else {
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
        background: "linear-gradient(135deg, rgba(15, 31, 43, 0.96), rgba(18, 39, 48, 0.92))",
        border: "1px solid rgba(74, 222, 200, 0.22)",
        boxShadow: "0 12px 32px rgba(0, 0, 0, 0.22), inset 0 1px 0 rgba(255, 255, 255, 0.04)",
      }}
    >
      <div
        style={{
          fontSize: "15px",
          fontWeight: 700,
          marginBottom: "8px",
          color: "#7ff7d4",
          display: "block",
          visibility: "visible",
          opacity: 1,
        }}
      >
        Key Insight
      </div>

      <div
        style={{
          fontSize: "14px",
          lineHeight: 1.6,
          color: "#d7e8e6",
          fontWeight: 500,
          display: "block",
          visibility: "visible",
          opacity: 1,
        }}
      >
        {cleanStoryText(story)}
      </div>
    </div>
  );
}





