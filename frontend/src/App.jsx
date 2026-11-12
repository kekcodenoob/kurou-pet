import { useState, useEffect } from "react";
// Each icon from lucide-react is its own React component you use like a custom tag,
// e.g. <Heart />. Common props: `size` (px), `color`, `strokeWidth`.
import { Heart, Smile, Angry, ChevronRight } from "lucide-react";
import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

const API_URL = "http://127.0.0.1:8000";
const REFRESH_MS = 5 * 60 * 1000; // How often to pull new stats from the pet
const RETRY_MS = 5 * 1000; // How often to retry while the pet isn't reachable yet

// Chart views. The pet logs activity in 5-minute buckets; the server groups them.
const INTERVALS = [
  {
    id: "5min",
    label: "5 minutes",
    caption: "Last 6 hours, in 5-minute increments",
    format: (d) => d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }),
  },
  {
    id: "day",
    label: "Daily",
    caption: "Last 30 days",
    format: (d) => d.toLocaleDateString([], { month: "short", day: "numeric" }),
  },
  {
    id: "month",
    label: "Monthly",
    caption: "Last 12 months",
    format: (d) => d.toLocaleDateString([], { month: "short", year: "2-digit" }),
  },
];

function App() {
  const [data, setData] = useState();

  // Tracks which source rows are expanded. Keys are source names, values are true.
  // We use an object (not just a single string) so multiple rows can be open at once.
  const [expanded, setExpanded] = useState({});
  const toggle = (source) =>
    setExpanded((prev) => ({ ...prev, [source]: !prev[source] }));

  const [history, setHistory] = useState([]);
  const [intervalId, setIntervalId] = useState("5min");
  const [lastUpdated, setLastUpdated] = useState(null);
  const view = INTERVALS.find((i) => i.id === intervalId);

  // Re-runs (and fetches right away) whenever the chart interval changes
  useEffect(() => {
    let timeoutId;
    let connected = false;
    let cancelled = false;

    async function fetchData() {
      try {
        const [statsResponse, historyResponse] = await Promise.all([
          fetch(`${API_URL}/`),
          fetch(`${API_URL}/history?interval=${intervalId}`),
        ]);
        const stats = await statsResponse.json();
        const points = await historyResponse.json();
        if (cancelled) return;
        setData(stats);
        setHistory(points);
        setLastUpdated(new Date());
        connected = true;
      } catch (err) {
        console.error("Failed to fetch:", err);
      }
      if (cancelled) return;
      // Retry quickly until the pet is reachable, then refresh every 5 minutes
      timeoutId = setTimeout(fetchData, connected ? REFRESH_MS : RETRY_MS);
    }

    fetchData();
    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
  }, [intervalId]);

  if (!data) return <p style={styles.loading}>Connecting to Kurou Pet...</p>;

  // `Icon` here holds the *component itself* (not yet rendered).
  // We render it below with <c.Icon ... />.
  const cards = [
    {
      label: "Affection Points",
      value: data.total_affection_points,
      accent: "#ff6b9d",
      Icon: Heart,
    },
    {
      label: "Happiness",
      value: data.total_happiness_count,
      accent: "#ffd93d",
      Icon: Smile,
    },
    {
      label: "Anger",
      value: data.total_anger_count,
      accent: "#ff6b6b",
      Icon: Angry,
    },
  ];

  // Group by source: one entry per site (e.g. "YouTube"), with its total time
  // and a nested list of individual tabs to show when expanded.
  // We only keep sources that have a `Tabs` object — other shapes are ignored.
  const sources = Object.entries(data.source_of_anger || {})
    .filter(([, info]) => info.Tabs)
    .map(([source, info]) => ({
      source,
      totalSeconds: info["Total seconds"] || 0,
      tabs: Object.entries(info.Tabs)
        .map(([title, seconds]) => ({ title, seconds }))
        .sort((a, b) => b.seconds - a.seconds),
    }))
    .sort((a, b) => b.totalSeconds - a.totalSeconds);

  // Max value drives the bar widths. Math.max(1, ...) avoids dividing by zero.
  const maxSeconds = Math.max(1, ...sources.map((s) => s.totalSeconds));

  const chartData = history.map((p) => ({ ...p, label: view.format(new Date(p.start)) }));
  const hasActivity = history.some(
    (p) => p.gained > 0 || p.lost > 0 || p.distracted_minutes > 0
  );

  return (
    <div style={styles.page}>
      <h1 style={styles.title}>Kurou Pet Dashboard</h1>
      <p style={styles.subtitle}>
        Last updated{" "}
        {lastUpdated?.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
        {" · "}refreshes every 5 minutes
      </p>

      <div style={styles.grid}>
        {cards.map((c) => (
          <div
            key={c.label}
            style={{ ...styles.card, border: `2px solid ${c.accent}` }}
          >
            <c.Icon size={28} color={c.accent} style={styles.cardIcon} />
            <div style={styles.cardValue}>{c.value ?? "—"}</div>
            <div style={styles.cardLabel}>{c.label}</div>
          </div>
        ))}
      </div>

      <div style={styles.section}>
        <h2 style={styles.sectionTitle}>Time per source</h2>
        {sources.length === 0 ? (
          <p style={styles.empty}>No tab activity yet.</p>
        ) : (
          sources.map((s) => {
            const isOpen = !!expanded[s.source];
            return (
              <div key={s.source} style={styles.sourceRow}>
                {/* The clickable header. A <button> is the right element for
                    "click to do something" — it's keyboard-accessible by default. */}
                <button
                  onClick={() => toggle(s.source)}
                  style={styles.sourceButton}
                >
                  <ChevronRight
                    size={18}
                    style={{
                      ...styles.chevron,
                      // Rotate the arrow when expanded. Pure CSS — no extra icon needed.
                      transform: isOpen ? "rotate(90deg)" : "rotate(0deg)",
                    }}
                  />
                  <span style={styles.sourceName}>{s.source}</span>
                  <span style={styles.sourceSeconds}>{s.totalSeconds}s</span>
                </button>

                <div style={styles.tabBarTrack}>
                  <div
                    style={{
                      ...styles.tabBarFill,
                      width: `${(s.totalSeconds / maxSeconds) * 100}%`,
                    }}
                  />
                </div>

                {/* `&&` short-circuit: if isOpen is false, nothing renders.
                    A common React pattern for "show this only when..." */}
                {isOpen && (
                  <div style={styles.tabList}>
                    {s.tabs.map((t) => (
                      <div key={t.title} style={styles.tabItem}>
                        <span style={styles.tabTitle} title={t.title}>
                          {t.title}
                        </span>
                        <span style={styles.tabSeconds}>{t.seconds}s</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      <div style={styles.section}>
        <div style={styles.chartHeader}>
          <div>
            <h2 style={{ ...styles.sectionTitle, marginBottom: 4 }}>Activity over time</h2>
            <p style={styles.empty}>{view.caption}</p>
          </div>
          <div style={styles.tabs} role="tablist">
            {INTERVALS.map((i) => (
              <button
                key={i.id}
                role="tab"
                aria-selected={i.id === intervalId}
                onClick={() => setIntervalId(i.id)}
                style={{
                  ...styles.tab,
                  ...(i.id === intervalId ? styles.tabActive : {}),
                }}
              >
                {i.label}
              </button>
            ))}
          </div>
        </div>

        {!hasActivity && (
          <p style={{ ...styles.empty, marginBottom: 12 }}>
            No activity recorded in this period yet. Bars fill in as you focus,
            work out, and get distracted.
          </p>
        )}
        <ResponsiveContainer width="100%" height={300}>
          <ComposedChart data={chartData} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#33334d" vertical={false} />
            <XAxis
              dataKey="label"
              stroke="#888"
              tick={{ fontSize: 11 }}
              interval="preserveStartEnd"
              minTickGap={24}
            />
            <YAxis yAxisId="points" stroke="#888" tick={{ fontSize: 11 }} allowDecimals={false} />
            <YAxis
              yAxisId="minutes"
              orientation="right"
              stroke="#888"
              tick={{ fontSize: 11 }}
              unit="m"
            />
            <Tooltip
              cursor={{ fill: "rgba(255,255,255,0.05)" }}
              contentStyle={{
                background: "#1a1a2e",
                border: "1px solid #33334d",
                borderRadius: 8,
              }}
            />
            <Legend />
            <Bar
              yAxisId="points"
              dataKey="gained"
              name="Affection earned"
              fill="#6bcb77"
              radius={[3, 3, 0, 0]}
            />
            <Bar
              yAxisId="points"
              dataKey="lost"
              name="Affection lost"
              fill="#ff6b6b"
              radius={[3, 3, 0, 0]}
            />
            <Line
              yAxisId="minutes"
              type="monotone"
              dataKey="distracted_minutes"
              name="Minutes distracted"
              stroke="#ffd93d"
              strokeWidth={2}
              dot={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

const styles = {
  page: {
    minHeight: "100vh",
    padding: "48px 24px",
    fontFamily: "system-ui, sans-serif",
    background: "#1a1a2e",
    color: "#f5f5f5",
  },
  loading: {
    textAlign: "center",
    marginTop: "40vh",
    fontFamily: "system-ui, sans-serif",
  },
  title: {
    textAlign: "center",
    marginBottom: 4,
    fontSize: 32,
  },
  subtitle: {
    textAlign: "center",
    marginTop: 0,
    marginBottom: 32,
    fontSize: 14,
    opacity: 0.6,
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
    gap: 16,
    maxWidth: 900,
    margin: "0 auto",
  },
  card: {
    background: "#262640",
    borderRadius: 12,
    padding: "24px 20px",
  },
  cardIcon: {
    marginBottom: 12,
  },
  cardLabel: {
    fontSize: 14,
    textTransform: "uppercase",
    letterSpacing: 0.5,
    marginTop: 8,
  },
  cardValue: {
    fontSize: 36,
    fontWeight: 600,
  },
  section: {
    maxWidth: 900,
    margin: "32px auto 0",
    background: "#262640",
    borderRadius: 12,
    padding: 24,
  },
  sectionTitle: {
    margin: "0 0 16px",
    fontSize: 20,
  },
  empty: {
    opacity: 0.6,
    margin: 0,
  },
  chartHeader: {
    display: "flex",
    flexWrap: "wrap",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 12,
    marginBottom: 16,
  },
  tabs: {
    display: "flex",
    background: "#1a1a2e",
    borderRadius: 8,
    padding: 3,
  },
  tab: {
    background: "transparent",
    border: "none",
    color: "inherit",
    font: "inherit",
    fontSize: 13,
    padding: "6px 12px",
    borderRadius: 6,
    cursor: "pointer",
    opacity: 0.7,
  },
  tabActive: {
    background: "#262640",
    opacity: 1,
    fontWeight: 600,
  },
  sourceRow: {
    padding: "12px 0",
    borderBottom: "1px solid #33334d",
  },
  sourceButton: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    width: "100%",
    background: "transparent",
    border: "none",
    color: "inherit",
    font: "inherit",
    padding: 0,
    cursor: "pointer",
    textAlign: "left",
    marginBottom: 8,
  },
  chevron: {
    transition: "transform 0.15s ease",
    flexShrink: 0,
    opacity: 0.7,
  },
  sourceName: {
    flex: 1,
    fontSize: 16,
    fontWeight: 600,
  },
  sourceSeconds: {
    fontSize: 16,
    fontWeight: 600,
    flexShrink: 0,
  },
  tabBarTrack: {
    height: 6,
    background: "#1a1a2e",
    borderRadius: 3,
    overflow: "hidden",
  },
  tabBarFill: {
    height: "100%",
    background: "#ff6b6b",
    borderRadius: 3,
  },
  tabList: {
    marginTop: 12,
    paddingLeft: 28,
    display: "flex",
    flexDirection: "column",
    gap: 6,
  },
  tabItem: {
    display: "flex",
    justifyContent: "space-between",
    gap: 12,
    fontSize: 13,
    opacity: 0.85,
  },
  tabTitle: {
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  tabSeconds: {
    fontWeight: 600,
    flexShrink: 0,
  },
};

export default App;
