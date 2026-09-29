import React from "react";

export default function CorrelationHeatmap({ data }) {
  const columns = Array.isArray(data?.columns)
    ? data.columns
    : [];

  const matrix = Array.isArray(data?.matrix)
    ? data.matrix
    : [];

  const getCorrelationLabel = (value) => {
    const absolute = Math.abs(value);

    if (absolute >= 0.8) return "Very strong";
    if (absolute >= 0.6) return "Strong";
    if (absolute >= 0.4) return "Moderate";
    if (absolute >= 0.2) return "Weak";
    return "Very weak";
  };

  return (
    <div className="correlation-map-wrapper">
      <div className="correlation-map-header">
        <div>
          <div className="correlation-map-eyebrow">
            STATISTICAL ANALYSIS
          </div>

          <h2>Correlation Matrix</h2>

          <p>
            Pearson correlation between numeric variables
          </p>
        </div>

        <div className="correlation-map-status">
          {columns.length} × {columns.length}
        </div>
      </div>

      {columns.length === 0 || matrix.length === 0 ? (
        <div className="correlation-empty">
          <div className="correlation-empty-title">
            Correlation data unavailable
          </div>

          <div className="correlation-empty-text">
            This dataset does not contain enough numeric variables
            to generate a correlation matrix.
          </div>
        </div>
      ) : (
        <>
          <div className="correlation-map-scroll">
            <div
              className="correlation-grid"
              style={{
                gridTemplateColumns:
                  `150px repeat(${columns.length}, minmax(85px, 1fr))`,
              }}
            >
              <div className="correlation-corner" />

              {columns.map((column) => (
                <div
                  key={`header-${column}`}
                  className="correlation-header"
                  title={column}
                >
                  {column}
                </div>
              ))}

              {matrix.map((row, rowIndex) => {
                const values = Array.isArray(row)
                  ? row
                  : Array.isArray(row?.values)
                  ? row.values
                  : [];

                return (
                  <React.Fragment key={`row-${rowIndex}`}>
                    <div
                      className="correlation-row-label"
                      title={columns[rowIndex]}
                    >
                      {columns[rowIndex] ||
                        `Variable ${rowIndex + 1}`}
                    </div>

                    {columns.map((_, colIndex) => {
                      const rawValue = values[colIndex];
                      const value = Number(rawValue);

                      const valid = Number.isFinite(value);
                      const intensity = valid
                        ? Math.min(Math.abs(value), 1)
                        : 0;

                      let background =
                        "rgba(100,116,139,0.16)";

                      if (valid && value >= 0) {
                        background =
                          `rgba(59,130,246,${0.18 + intensity * 0.72})`;
                      } else if (valid && value < 0) {
                        background =
                          `rgba(239,68,68,${0.18 + intensity * 0.72})`;
                      }

                      return (
                        <div
                          key={`${rowIndex}-${colIndex}`}
                          className={`correlation-cell ${
                            valid && Math.abs(value) >= 0.8
                              ? "correlation-cell-strong"
                              : ""
                          }`}
                          style={{ background }}
                          title={
                            valid
                              ? `${columns[rowIndex]} × ${columns[colIndex]}: ${value.toFixed(
                                  2
                                )} — ${getCorrelationLabel(value)}`
                              : "No correlation value"
                          }
                        >
                          {valid
                            ? value.toFixed(2)
                            : "—"}
                        </div>
                      );
                    })}
                  </React.Fragment>
                );
              })}
            </div>
          </div>

          <div className="correlation-interpretation">
            <div className="correlation-interpretation-title">
              How to read this matrix
            </div>

            <div className="correlation-interpretation-text">
              Values closer to <strong>+1</strong> indicate a strong
              positive linear relationship, while values closer to{" "}
              <strong>-1</strong> indicate a strong negative linear
              relationship. Values near <strong>0</strong> indicate
              little linear relationship.
            </div>
          </div>
        </>
      )}

      <div className="correlation-legend">
        <span>
          <i className="correlation-positive" />
          Positive
        </span>

        <span>
          <i className="correlation-negative" />
          Negative
        </span>

        <span>
          Values range from −1 to +1
        </span>
      </div>
    </div>
  );
}
