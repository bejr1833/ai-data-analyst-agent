import React from "react";

export default function ColumnTable({ columns }) {
  if (!columns?.length) return null;
  return (
    <section className="panel">
      <h2 className="panel-title">Column profile</h2>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Column</th>
              <th>Type</th>
              <th>Missing</th>
              <th>Distinct</th>
              <th>Mean</th>
              <th>Std</th>
              <th>Min</th>
              <th>Max</th>
            </tr>
          </thead>
          <tbody>
            {columns.map((c) => (
              <tr key={c.column}>
                <td className="mono">{c.column}</td>
                <td>{c.dtype}</td>
                <td>{c.missing_pct}%</td>
                <td>{c.distinct_count.toLocaleString()}</td>
                <td className="mono">{c.type === "numeric" ? c.mean ?? "—" : "—"}</td>
                <td className="mono">{c.type === "numeric" ? c.std ?? "—" : "—"}</td>
                <td className="mono">{c.type === "numeric" ? c.min ?? "—" : "—"}</td>
                <td className="mono">{c.type === "numeric" ? c.max ?? "—" : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}


