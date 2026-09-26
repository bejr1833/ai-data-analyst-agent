import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

export default function CategoricalGrid({ charts }) {
  if (!charts?.length) return null;
  return (
    <section className="panel">
      <h2 className="panel-title">Categorical breakdowns</h2>
      <div className="chart-grid">
        {charts.map((c) => {
          if (!c.categories?.length) return null;
          const data = c.categories.map((cat, i) => ({ category: cat, count: c.counts[i] }));
          return (
            <div className="chart-card" key={c.column}>
              <div className="chart-card-title">{c.column}</div>
              <ResponsiveContainer width="100%" height={Math.max(180, data.length * 26)}>
                <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 0, left: 4 }}>
                  <CartesianGrid strokeDasharray="2 4" stroke="#D9DED9" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 9, fontFamily: "IBM Plex Mono" }} />
                  <YAxis
                    dataKey="category"
                    type="category"
                    width={110}
                    tick={{ fontSize: 10, fontFamily: "IBM Plex Sans" }}
                  />
                  <Tooltip contentStyle={{ fontSize: 12, fontFamily: "IBM Plex Mono" }} />
                  <Bar dataKey="count" fill="#D96C2C" radius={[0, 2, 2, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          );
        })}
      </div>
    </section>
  );
}
