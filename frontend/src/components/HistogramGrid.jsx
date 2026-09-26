import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

export default function HistogramGrid({ histograms }) {
  if (!histograms?.length) return null;
  return (
    <section className="panel">
      <h2 className="panel-title">Numeric distributions</h2>
      <div className="chart-grid">
        {histograms.map((h) => {
          if (!h.counts?.length) return null;
          const data = h.counts.map((c, i) => ({
            bucket: h.bin_edges.length > i + 1 ? h.bin_edges[i].toFixed(2) : i,
            count: c,
          }));
          return (
            <div className="chart-card" key={h.column}>
              <div className="chart-card-title">{h.column}</div>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
                  <CartesianGrid strokeDasharray="2 4" stroke="#D9DED9" vertical={false} />
                  <XAxis dataKey="bucket" tick={{ fontSize: 9, fontFamily: "IBM Plex Mono" }} interval={Math.ceil(data.length / 6)} />
                  <YAxis tick={{ fontSize: 9, fontFamily: "IBM Plex Mono" }} width={34} />
                  <Tooltip contentStyle={{ fontSize: 12, fontFamily: "IBM Plex Mono" }} />
                  <Bar dataKey="count" fill="#0F6E67" radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          );
        })}
      </div>
    </section>
  );
}
