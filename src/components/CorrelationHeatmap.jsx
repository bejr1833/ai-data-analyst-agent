import React from "react";

export default function CorrelationHeatmap({ data }) {
  // Safely handle missing correlation data
  if (!data) {
    return (
      <div className="chart-card">
        <h3>Correlation Heatmap</h3>
        <p className="muted">No correlation data available.</p>
      </div>
    );
  }

  // Support either:
  // { columns: [...], matrix: [...] }
  // or
  // { labels: [...], matrix: [...] }
  const columns = data.columns || data.labels || [];
  const matrix = data.matrix || [];

  if (!columns.length || !matrix.length) {
    return (
      <div className="chart-card">
        <h3>Correlation Heatmap</h3>
        <p className="muted">
          Correlation data is not available for this dataset.
        </p>
      </div>
    );
  }

  return (
    <div className="chart-card">
      <h3>Correlation Heatmap</h3>

      <div
        style={{
          overflowX: "auto",
          overflowY: "auto",
          maxHeight: "500px",
        }}
      >
        <table
          style={{
            borderCollapse: "collapse",
            width: "100%",
            minWidth: "600px",
          }}
        >
          <thead>
            <tr>
              <th
                style={{
                  padding: "8px",
                  textAlign: "left",
                }}
              >
                Variable
              </th>

              {columns.map((column) => (
                <th
                  key={column}
                  style={{
                    padding: "8px",
                    textAlign: "center",
                    fontSize: "12px",
                  }}
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {matrix.map((row, rowIndex) => {
              const values = Array.isArray(row)
                ? row
                : row.values || [];

              return (
                <tr key={rowIndex}>
                  <th
                    style={{
                      padding: "8px",
                      textAlign: "left",
                      fontSize: "12px",
                    }}
                  >
                    {columns[rowIndex] || `Variable ${rowIndex + 1}`}
                  </th>

                  {columns.map((_, colIndex) => {
                    const value = Number(values[colIndex]);

                    const displayValue = Number.isFinite(value)
                      ? value.toFixed(2)
                      : "—";

                    return (
                      <td
                        key={colIndex}
                        style={{
                          padding: "8px",
                          textAlign: "center",
                          fontSize: "12px",
                        }}
                      >
                        {displayValue}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}