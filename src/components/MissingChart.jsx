import React from "react";

import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

export default function MissingChart({ missing }) {
  if (!missing?.columns?.length) {
    return (
      <section className="panel">
        <h2 className="panel-title">Missing data</h2>
        <p className="empty-note">No missing values detected across any column.</p>
      </section>
    );
  }
  const data = missing.columns.map((col, i) => ({ column: col, pct: missing.missing_pct[i] }));
  return (
    <section className="panel">
      <h2 className="panel-title">Missing data by column</h2>
      <ResponsiveContainer width="100%" height={Math.max(200, data.length * 28)}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, bottom: 0, left: 4 }}>
          <CartesianGrid strokeDasharray="2 4" stroke="#D9DED9" horizontal={false} />
          <XAxis type="number" unit="%" tick={{ fontSize: 9, fontFamily: "IBM Plex Mono" }} />
          <YAxis dataKey="column" type="category" width={140} tick={{ fontSize: 10, fontFamily: "IBM Plex Sans" }} />
          <Tooltip contentStyle={{ fontSize: 12, fontFamily: "IBM Plex Mono" }} formatter={(v) => `${v}%`} />
          <Bar dataKey="pct" fill="#B3462C" radius={[0, 2, 2, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
}

