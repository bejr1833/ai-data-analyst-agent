import React from "react";

function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "";

  const number = Number(value);

  if (!Number.isFinite(number)) return String(value);

  return number.toLocaleString("en-IN", {
    maximumFractionDigits: 2,
  });
}

function formatCompact(value) {
  const number = Number(value);

  if (!Number.isFinite(number)) return String(value ?? "");

  return number.toLocaleString("en-IN", {
    notation: "compact",
    maximumFractionDigits: 1,
  });
}

function niceTicks(min, max, count = 5) {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [];

  if (min === max) {
    return [min];
  }

  const rawStep = (max - min) / Math.max(1, count - 1);
  const magnitude = 10 ** Math.floor(Math.log10(Math.abs(rawStep)));
  const normalized = rawStep / magnitude;

  let niceStep;
  if (normalized <= 1) niceStep = 1;
  else if (normalized <= 2) niceStep = 2;
  else if (normalized <= 5) niceStep = 5;
  else niceStep = 10;

  niceStep *= magnitude;

  const start = Math.floor(min / niceStep) * niceStep;
  const end = Math.ceil(max / niceStep) * niceStep;

  const ticks = [];
  for (let value = start; value <= end + niceStep * 0.001; value += niceStep) {
    ticks.push(Number(value.toFixed(10)));
  }

  return ticks;
}

function axisTitle(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function chartTitle(visualization, x, y) {
  return (
    visualization?.title ||
    `${axisTitle(y)} by ${axisTitle(x)}`
  );
}

function Label({ x, y, children, anchor = "middle", fill = "#EAF2FA" }) {
  return (
    <text
      x={x}
      y={y}
      textAnchor={anchor}
      fill={fill}
      fontSize="11"
      fontWeight="600"
      paintOrder="stroke"
      stroke="rgba(7, 18, 32, .88)"
      strokeWidth="3"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {children}
    </text>
  );
}

function ChartFrame({ title, children, footer }) {
  return (
    <div
      className="analysis-chart-card"
      style={{
        width: "100%",
        maxWidth: "100%",
        marginTop: 18,
        padding: "18px 18px 14px",
        boxSizing: "border-box",
        border: "1px solid rgba(159,181,211,.16)",
        borderRadius: 16,
        background: "rgba(20,32,51,.78)",
        overflow: "visible",
      }}
    >
      <div
        style={{
          marginBottom: 12,
          color: "#EDF3F8",
          fontSize: 15,
          fontWeight: 700,
          letterSpacing: ".01em",
        }}
      >
        {title}
      </div>

      {children}

      {footer && (
        <div
          style={{
            marginTop: 8,
            color: "#91A2B7",
            fontSize: 12,
            lineHeight: 1.5,
          }}
        >
          {footer}
        </div>
      )}
    </div>
  );
}

function BarChart({ rows, x, y, visualization }) {
  const data = rows
    .map((row) => ({
      label: String(row?.[x] ?? ""),
      value: Number(row?.[y]),
    }))
    .filter((item) => item.label && Number.isFinite(item.value));

  if (!data.length) return null;

  const width = 1000;
  const height = 480;
  const left = 96;
  const right = 34;
  const top = 48;
  const bottom = data.length > 8 ? 118 : 92;

  const chartWidth = width - left - right;
  const chartHeight = height - top - bottom;

  const minValue = Math.min(0, ...data.map((item) => item.value));
  const maxValue = Math.max(0, ...data.map((item) => item.value));
  const ticks = niceTicks(minValue, maxValue, 5);

  const scaleMin = ticks.length ? ticks[0] : minValue;
  const scaleMax = ticks.length ? ticks[ticks.length - 1] : maxValue;
  const range = scaleMax - scaleMin || 1;

  const yPos = (value) =>
    top + ((scaleMax - value) / range) * chartHeight;

  const slot = chartWidth / data.length;
  const barWidth = Math.max(
    18,
    Math.min(64, slot * 0.62)
  );

  const palette = [
    "#6B8FD3",
    "#9A7BB5",
    "#5E9C7A",
    "#C49A5A",
    "#B86F7C",
    "#5F9EA8",
    "#8B8FA8",
    "#A67C52",
  ];

  const showEveryValue = data.length <= 15;

  return (
    <ChartFrame title={chartTitle(visualization, x, y)}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        height="480"
        preserveAspectRatio="none"
        role="img"
        aria-label={chartTitle(visualization, x, y)}
        style={{ display: "block", width: "100%", height: 480 }}
      >
        {ticks.map((tick, index) => {
          const py = yPos(tick);

          return (
            <g key={`grid-${index}`}>
              <line
                x1={left}
                x2={width - right}
                y1={py}
                y2={py}
                stroke="rgba(159,181,211,.14)"
                strokeDasharray="4 5"
              />
              <text
                x={left - 12}
                y={py + 4}
                textAnchor="end"
                fill="#DCE7F5"
                fontSize="12"
                fontWeight="600"
              >
                {formatCompact(tick)}
              </text>
            </g>
          );
        })}

        <line
          x1={left}
          x2={left}
          y1={top}
          y2={height - bottom}
          stroke="#8196AD"
          strokeWidth="1.4"
        />

        <line
          x1={left}
          x2={width - right}
          y1={yPos(0)}
          y2={yPos(0)}
          stroke="#8196AD"
          strokeWidth="1.2"
        />

        {data.map((item, index) => {
          const cx = left + slot * index + slot / 2;
          const valueY = yPos(item.value);
          const zeroY = yPos(0);
          const barY = Math.min(valueY, zeroY);
          const barHeight = Math.max(
            2,
            Math.abs(zeroY - valueY)
          );

          return (
            <g key={`${item.label}-${index}`}>
              <rect
                x={cx - barWidth / 2}
                y={barY}
                width={barWidth}
                height={barHeight}
                rx="5"
                fill={palette[index % palette.length]}
                opacity="0.92"
              />

              {showEveryValue && (
                <Label
                  x={cx}
                  y={barY - 9}
                >
                  {formatNumber(item.value)}
                </Label>
              )}

              <text
                x={cx}
                y={height - bottom + 31}
                textAnchor="middle"
                fill="#F0F6FC"
                fontSize="13"
                fontWeight="700"
                paintOrder="stroke"
                stroke="rgba(7,18,32,.92)"
                strokeWidth="3"
                transform={
                  data.length > 8
                    ? `rotate(-32 ${cx} ${height - bottom + 28})`
                    : undefined
                }
              >
                {item.label.length > 18
                  ? `${item.label.slice(0, 17)}…`
                  : item.label}
              </text>
            </g>
          );
        })}

        <text
          x={left + chartWidth / 2}
          y={height - 12}
          textAnchor="middle"
          fill="#91A2B7"
          fontSize="13"
          fontWeight="700"
        >
          {axisTitle(x)}
        </text>

        <text
          x="17"
          y={top + chartHeight / 2}
          textAnchor="middle"
          fill="#91A2B7"
          fontSize="13"
          fontWeight="700"
          transform={`rotate(-90 17 ${top + chartHeight / 2})`}
        >
          {axisTitle(y)}
        </text>
      </svg>

      {!showEveryValue && (
        <div
          style={{
            marginTop: 2,
            color: "#71839A",
            fontSize: 11,
          }}
        >
          Hover-style detail is represented by the axis scale; individual
          values are listed in the analysis table below.
        </div>
      )}
    </ChartFrame>
  );
}

function LineChart({ rows, x, y, visualization, forecastY }) {
  const data = rows
    .map((row) => ({
      label: String(row?.[x] ?? ""),
      value:
        row?.[y] === null || row?.[y] === undefined
          ? null
          : Number(row[y]),
      forecast:
        row?.[forecastY] === null ||
        row?.[forecastY] === undefined
          ? null
          : Number(row[forecastY]),
    }))
    .filter(
      (item) =>
        item.label &&
        (Number.isFinite(item.value) ||
          Number.isFinite(item.forecast))
    );

  if (!data.length) return null;

  const allValues = data.flatMap((item) =>
    [item.value, item.forecast].filter(Number.isFinite)
  );

  const width = 1000;
  const height = 470;
  const left = 92;
  const right = 34;
  const top = 48;
  const bottom = data.length > 8 ? 112 : 82;

  const chartWidth = width - left - right;
  const chartHeight = height - top - bottom;

  const minValue = Math.min(0, ...allValues);
  const maxValue = Math.max(...allValues);
  const ticks = niceTicks(minValue, maxValue, 5);

  const scaleMin = ticks.length ? ticks[0] : minValue;
  const scaleMax = ticks.length ? ticks[ticks.length - 1] : maxValue;
  const range = scaleMax - scaleMin || 1;

  const xPos = (index) =>
    left +
    (data.length === 1
      ? chartWidth / 2
      : (index / (data.length - 1)) * chartWidth);

  const yPos = (value) =>
    top + ((scaleMax - value) / range) * chartHeight;

  const makePath = (key) => {
    const points = data
      .map((item, index) =>
        Number.isFinite(item[key])
          ? `${xPos(index)},${yPos(item[key])}`
          : null
      )
      .filter(Boolean);

    return points.join(" ");
  };

  const historicalPath = makePath("value");
  const forecastPath = makePath("forecast");
  const forecastIndices = data
    .map((item, index) =>
      Number.isFinite(item.forecast) ? index : null
    )
    .filter((index) => index !== null);

  const firstForecastIndex =
    forecastIndices.length ? forecastIndices[0] : -1;

  // Keep labels readable instead of printing every historical date.
  const labelStep = Math.max(
    1,
    Math.ceil(data.length / 8)
  );

  const shouldShowXLabel = (index) =>
    data.length <= 8 ||
    index === 0 ||
    index === data.length - 1 ||
    index % labelStep === 0 ||
    forecastIndices.includes(index);

  return (
    <ChartFrame title={chartTitle(visualization, x, y)}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        height="470"
        preserveAspectRatio="none"
        role="img"
        aria-label={chartTitle(visualization, x, y)}
        style={{
          display: "block",
          width: "100%",
          height: 470,
        }}
      >
        {ticks.map((tick, index) => {
          const py = yPos(tick);

          return (
            <g key={`grid-${index}`}>
              <line
                x1={left}
                x2={width - right}
                y1={py}
                y2={py}
                stroke="rgba(190,205,225,.16)"
                strokeDasharray="4 5"
              />

              <text
                x={left - 14}
                y={py + 4}
                textAnchor="end"
                fill="#D5E0EC"
                fontSize="12"
                fontWeight="600"
              >
                {formatCompact(tick)}
              </text>
            </g>
          );
        })}

        <line
          x1={left}
          x2={left}
          y1={top}
          y2={height - bottom}
          stroke="#8093AA"
          strokeWidth="1.2"
        />

        <line
          x1={left}
          x2={width - right}
          y1={height - bottom}
          y2={height - bottom}
          stroke="#8093AA"
          strokeWidth="1.2"
        />

        {/* Historical series */}
        <polyline
          fill="none"
          points={historicalPath}
          stroke="#4FC3B5"
          strokeWidth="4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {data.map((item, index) =>
          Number.isFinite(item.value) ? (
            <g key={`history-${index}`}>
              <circle
                cx={xPos(index)}
                cy={yPos(item.value)}
                r="5"
                fill="#4FC3B5"
                stroke="#E8FFFA"
                strokeWidth="1"
              />

              {/* Show historical values only when there are few points. */}
              {data.length <= 12 && (
                <Label
                  x={xPos(index)}
                  y={yPos(item.value) - 13}
                  fill="#F4FFFD"
                >
                  {formatNumber(item.value)}
                </Label>
              )}
            </g>
          ) : null
        )}

        {/* Forecast series */}
        {forecastPath && (
          <>
            <polyline
              fill="none"
              points={forecastPath}
              stroke="#F2B86B"
              strokeWidth="4"
              strokeDasharray="10 6"
              strokeLinecap="round"
              strokeLinejoin="round"
            />

            {data.map((item, index) =>
              Number.isFinite(item.forecast) ? (
                <g key={`forecast-${index}`}>
                  <circle
                    cx={xPos(index)}
                    cy={yPos(item.forecast)}
                    r="6"
                    fill="#F2B86B"
                    stroke="#FFF5E8"
                    strokeWidth="1.5"
                  />

                  {/* Forecast values remain visible even when history is long. */}
                  <Label
                    x={xPos(index)}
                    y={yPos(item.forecast) - 15}
                    fill="#FFF7EA"
                  >
                    {formatNumber(item.forecast)}
                  </Label>
                </g>
              ) : null
            )}
          </>
        )}

        {/* X-axis labels: selectively shown so dates never become a text wall. */}
        {data.map((item, index) =>
          shouldShowXLabel(index) ? (
            <g key={`label-${index}`}>
              <text
                x={xPos(index)}
                y={height - bottom + 27}
                textAnchor="middle"
                fill="#D5E0EC"
                fontSize="11"
                fontWeight="600"
                transform={
                  data.length > 8
                    ? `rotate(-30 ${xPos(index)} ${height - bottom + 27})`
                    : undefined
                }
              >
                {item.label.length > 16
                  ? `${item.label.slice(0, 15)}…`
                  : item.label}
              </text>
            </g>
          ) : null
        )}

        {/* Axis titles */}
        <text
          x={left + chartWidth / 2}
          y={height - 12}
          textAnchor="middle"
          fill="#E3EDF7"
          fontSize="13"
          fontWeight="700"
        >
          {axisTitle(x)}
        </text>

        <text
          x="20"
          y={top + chartHeight / 2}
          textAnchor="middle"
          fill="#E3EDF7"
          fontSize="13"
          fontWeight="700"
          transform={`rotate(-90 20 ${top + chartHeight / 2})`}
        >
          {axisTitle(y)}
        </text>

        {/* Forecast transition marker */}
        {firstForecastIndex > 0 && (
          <line
            x1={xPos(firstForecastIndex)}
            x2={xPos(firstForecastIndex)}
            y1={top}
            y2={height - bottom}
            stroke="rgba(242,184,107,.30)"
            strokeWidth="2"
            strokeDasharray="5 5"
          />
        )}
      </svg>

      <div
        style={{
          display: "flex",
          gap: 22,
          flexWrap: "wrap",
          marginTop: 4,
          paddingTop: 6,
          color: "#D5E0EC",
          fontSize: 12,
          fontWeight: 600,
        }}
      >
        <span>
          <span style={{ color: "#4FC3B5" }}>●</span>{" "}
          {isForecastLabel(visualization)
            ? "Historical"
            : axisTitle(y)}
        </span>

        {isForecastLabel(visualization) && (
          <span>
            <span style={{ color: "#F2B86B" }}>●</span>{" "}
            Forecast
          </span>
        )}
      </div>
    </ChartFrame>
  );
}

function isForecastLabel(visualization) {
  return visualization?.type === "forecast";
}

function ScatterChart({ rows, x, y, visualization }) {
  const data = rows
    .map((row, index) => ({
      index: index + 1,
      x: Number(row?.[x]),
      y: Number(row?.[y]),
    }))
    .filter(
      (point) =>
        Number.isFinite(point.x) &&
        Number.isFinite(point.y)
    );

  if (!data.length) return null;

  const width = 1000;
  const height = 430;
  const left = 88;
  const right = 32;
  const top = 42;
  const bottom = 74;

  const chartWidth = width - left - right;
  const chartHeight = height - top - bottom;

  const xValues = data.map((point) => point.x);
  const yValues = data.map((point) => point.y);

  const xTicks = niceTicks(
    Math.min(...xValues),
    Math.max(...xValues),
    5
  );

  const yTicks = niceTicks(
    Math.min(...yValues),
    Math.max(...yValues),
    5
  );

  const xMin = xTicks[0] ?? Math.min(...xValues);
  const xMax = xTicks[xTicks.length - 1] ?? Math.max(...xValues);
  const yMin = yTicks[0] ?? Math.min(...yValues);
  const yMax = yTicks[yTicks.length - 1] ?? Math.max(...yValues);

  const xRange = xMax - xMin || 1;
  const yRange = yMax - yMin || 1;

  const xPos = (value) =>
    left + ((value - xMin) / xRange) * chartWidth;

  const yPos = (value) =>
    top + ((yMax - value) / yRange) * chartHeight;

  const correlation = pearsonCorrelation(
    xValues,
    yValues
  );

  return (
    <ChartFrame
      title={chartTitle(visualization, x, y)}
      footer={
        <span>
          Pearson correlation:{" "}
          <strong style={{ color: "#EDF3F8" }}>
            {Number.isFinite(correlation)
              ? correlation.toFixed(4)
              : "—"}
          </strong>
          {" · "}
          {data.length} observations
        </span>
      }
    >
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        height="430"
        preserveAspectRatio="none"
        role="img"
        aria-label={chartTitle(visualization, x, y)}
        style={{ display: "block", width: "100%", height: 430 }}
      >
        {yTicks.map((tick, index) => {
          const py = yPos(tick);

          return (
            <g key={`y-grid-${index}`}>
              <line
                x1={left}
                x2={width - right}
                y1={py}
                y2={py}
                stroke="rgba(159,181,211,.14)"
                strokeDasharray="4 5"
              />
              <text
                x={left - 12}
                y={py + 4}
                textAnchor="end"
                fill="#91A2B7"
                fontSize="11"
              >
                {formatCompact(tick)}
              </text>
            </g>
          );
        })}

        {xTicks.map((tick, index) => {
          const px = xPos(tick);

          return (
            <g key={`x-grid-${index}`}>
              <line
                x1={px}
                x2={px}
                y1={top}
                y2={height - bottom}
                stroke="rgba(159,181,211,.10)"
                strokeDasharray="4 5"
              />
              <text
                x={px}
                y={height - bottom + 25}
                textAnchor="middle"
                fill="#91A2B7"
                fontSize="11"
              >
                {formatCompact(tick)}
              </text>
            </g>
          );
        })}

        <line
          x1={left}
          x2={left}
          y1={top}
          y2={height - bottom}
          stroke="rgba(190,205,225,.30)"
        />

        <line
          x1={left}
          x2={width - right}
          y1={height - bottom}
          y2={height - bottom}
          stroke="rgba(190,205,225,.30)"
        />

        {data.map((point) => (
          <circle
            key={`point-${point.index}`}
            cx={xPos(point.x)}
            cy={yPos(point.y)}
            r="6"
            fill="#6B8FD3"
            fillOpacity="0.86"
            stroke="#DCE7F4"
            strokeWidth="1"
          />
        ))}

        <text
          x={left + chartWidth / 2}
          y={height - 12}
          textAnchor="middle"
          fill="#E3EDF7"
          fontSize="13"
          fontWeight="700"
        >
          {axisTitle(x)}
        </text>

        <text
          x="17"
          y={top + chartHeight / 2}
          textAnchor="middle"
          fill="#E3EDF7"
          fontSize="13"
          fontWeight="700"
          transform={`rotate(-90 17 ${top + chartHeight / 2})`}
        >
          {axisTitle(y)}
        </text>

        <g>
          <rect
            x={width - 190}
            y={top - 25}
            width="155"
            height="28"
            rx="8"
            fill="rgba(107,143,211,.16)"
            stroke="rgba(107,143,211,.30)"
          />
          <text
            x={width - 112}
            y={top - 7}
            textAnchor="middle"
            fill="#DCE7F4"
            fontSize="12"
            fontWeight="700"
          >
            r ={" "}
            {Number.isFinite(correlation)
              ? correlation.toFixed(4)
              : "—"}
          </text>
        </g>
      </svg>
    </ChartFrame>
  );
}

function pearsonCorrelation(xs, ys) {
  if (xs.length !== ys.length || xs.length < 2) return NaN;

  const meanX =
    xs.reduce((sum, value) => sum + value, 0) / xs.length;
  const meanY =
    ys.reduce((sum, value) => sum + value, 0) / ys.length;

  let numerator = 0;
  let denominatorX = 0;
  let denominatorY = 0;

  for (let index = 0; index < xs.length; index += 1) {
    const dx = xs[index] - meanX;
    const dy = ys[index] - meanY;

    numerator += dx * dy;
    denominatorX += dx * dx;
    denominatorY += dy * dy;
  }

  const denominator =
    Math.sqrt(denominatorX * denominatorY);

  return denominator === 0
    ? NaN
    : numerator / denominator;
}

export default function AnalysisChart({
  rows = [],
  visualization = {},
}) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return null;
  }

  const {
    type = "bar",
    x,
    y,
    forecastY = "forecast",
  } = visualization;

  if (!x || !y) return null;

  if (type === "scatter") {
    return (
      <ScatterChart
        rows={rows}
        x={x}
        y={y}
        visualization={visualization}
      />
    );
  }

  if (type === "line") {
    return (
      <LineChart
        rows={rows}
        x={x}
        y={y}
        visualization={visualization}
        forecastY={forecastY}
      />
    );
  }

  if (type === "forecast") {
    return (
      <LineChart
        rows={rows}
        x={x}
        y={y}
        visualization={visualization}
        forecastY={forecastY}
      />
    );
  }

  return (
    <BarChart
      rows={rows}
      x={x}
      y={y}
      visualization={visualization}
    />
  );
}
