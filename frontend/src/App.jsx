import { useState, useEffect } from "react";
// Each icon from lucide-react is its own React component you use like a custom tag,
// e.g. <Heart />. Common props: `size` (px), `color`, `strokeWidth`.
import { Heart, Smile, Angry, ChevronRight, Dumbbell } from "lucide-react";
import {
  ComposedChart,
  BarChart,
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
  const [workouts, setWorkouts] = useState(null);
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
        const [statsResponse, historyResponse, workoutsResponse] = await Promise.all([
          fetch(`${API_URL}/`),
          fetch(`${API_URL}/history?interval=${intervalId}`),
          fetch(`${API_URL}/workouts`),
        ]);
        const stats = await statsResponse.json();
        const points = await historyResponse.json();
        const workoutStats = await workoutsResponse.json();
        if (cancelled) return;
        setData(stats);
        setHistory(points);
        setWorkouts(workoutStats);
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

  // Time per source: one entry per site (e.g. "YouTube"), with its total time
  // and a nested list of individual tabs to show when expanded.
  // We only keep sources that have a `Tabs` object — other shapes are ignored.
  const distractionSources = toSourceRows(data.source_of_anger, "Total seconds", "Tabs");

  // Affection per source: same shape, e.g. "Workouts" -> { "Bicep Curls": 30 }
  const affectionSources = toSourceRows(data.source_of_happiness, "Total points", "Breakdown");

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

      <SourceList
        title="Affection per source"
        rows={affectionSources}
        unit=" pts"
        color="#6bcb77"
        emptyText="No affection earned yet. Focus, work out, or pet your pet."
        expanded={expanded}
        toggle={toggle}
        keyPrefix="affection"
      />

      <SourceList
        title="Time per anger source"
        rows={distractionSources}
        unit="s"
        color="#ff6b6b"
        emptyText="No tab activity yet."
        expanded={expanded}
        toggle={toggle}
        keyPrefix="distraction"
      />

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
              contentStyle={styles.tooltip}
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

      <WorkoutSection workouts={workouts} chartData={chartData} caption={view.caption} />
    </div>
  );
}

// Turns {"YouTube": {"Total seconds": 35, "Tabs": {...}}} into sorted rows for SourceList
function toSourceRows(sources, totalKey, detailKey) {
  return Object.entries(sources || {})
    .filter(([, info]) => info && info[detailKey])
    .map(([source, info]) => ({
      source,
      total: info[totalKey] || 0,
      details: Object.entries(info[detailKey])
        .map(([title, amount]) => ({ title, amount }))
        .sort((a, b) => b.amount - a.amount),
    }))
    .sort((a, b) => b.total - a.total);
}

// Expandable list of sources: a bar per total, with a breakdown underneath
function SourceList({ title, rows, unit, color, emptyText, expanded, toggle, keyPrefix }) {
  // Max value drives the bar widths. Math.max(1, ...) avoids dividing by zero.
  const max = Math.max(1, ...rows.map((r) => r.total));
  return (
    <div style={styles.section}>
      <h2 style={styles.sectionTitle}>{title}</h2>
      {rows.length === 0 ? (
        <p style={styles.empty}>{emptyText}</p>
      ) : (
        rows.map((r) => {
          const key = `${keyPrefix}:${r.source}`;
          const isOpen = !!expanded[key];
          return (
            <div key={key} style={styles.sourceRow}>
              {/* A <button> is the right element for "click to do something":
                  it's keyboard-accessible by default. */}
              <button onClick={() => toggle(key)} style={styles.sourceButton}>
                <ChevronRight
                  size={18}
                  style={{
                    ...styles.chevron,
                    // Rotate the arrow when expanded. Pure CSS, no extra icon needed.
                    transform: isOpen ? "rotate(90deg)" : "rotate(0deg)",
                  }}
                />
                <span style={styles.sourceName}>{r.source}</span>
                <span style={styles.sourceSeconds}>
                  {r.total}
                  {unit}
                </span>
              </button>

              <div style={styles.tabBarTrack}>
                <div
                  style={{
                    ...styles.tabBarFill,
                    background: color,
                    width: `${(r.total / max) * 100}%`,
                  }}
                />
              </div>

              {/* `&&` short-circuit: if isOpen is false, nothing renders. */}
              {isOpen && (
                <div style={styles.tabList}>
                  {r.details.map((d) => (
                    <div key={d.title} style={styles.tabItem}>
                      <span style={styles.tabTitle} title={d.title}>
                        {d.title}
                      </span>
                      <span style={styles.tabSeconds}>
                        {d.amount}
                        {unit}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })
      )}
    </div>
  );
}

const formatWhen = (ms) =>
  new Date(ms).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });

const percent = (part, whole) => (whole ? `${Math.round((part / whole) * 100)}%` : "—");

// Workout totals, reps per period (same interval as the activity chart),
// per-exercise totals, and the latest sessions
function WorkoutSection({ workouts, chartData, caption }) {
  const hasWorkouts = workouts && workouts.total_sessions > 0;
  const hasReps = chartData.some((p) => p.workout_reps > 0);
  return (
    <div style={styles.section}>
      <h2 style={styles.sectionTitle}>
        <Dumbbell size={20} style={styles.titleIcon} />
        Workouts
      </h2>
      {!hasWorkouts ? (
        <p style={styles.empty}>
          No workouts yet. Right-click the pet and pick an exercise under Workout.
        </p>
      ) : (
        <>
          <div style={styles.statRow}>
            <Stat label="Sessions" value={workouts.total_sessions} />
            <Stat label="Reps" value={workouts.total_reps} />
            <Stat
              label="Good form"
              value={percent(workouts.total_good_form_reps, workouts.total_reps)}
            />
          </div>

          <h3 style={styles.subTitle}>Reps over time</h3>
          <p style={{ ...styles.empty, marginBottom: 8 }}>
            {hasReps ? caption : `No reps in this period (${caption.toLowerCase()}).`}
          </p>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#33334d" vertical={false} />
              <XAxis
                dataKey="label"
                stroke="#888"
                tick={{ fontSize: 11 }}
                interval="preserveStartEnd"
                minTickGap={24}
              />
              <YAxis stroke="#888" tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip cursor={{ fill: "rgba(255,255,255,0.05)" }} contentStyle={styles.tooltip} />
              <Bar
                dataKey="workout_reps"
                name="Reps"
                fill="#4d96ff"
                radius={[3, 3, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>

          <h3 style={styles.subTitle}>By exercise</h3>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Exercise</th>
                <th style={styles.thNum}>Sessions</th>
                <th style={styles.thNum}>Reps</th>
                <th style={styles.thNum}>Good form</th>
                <th style={styles.thNum}>Points</th>
              </tr>
            </thead>
            <tbody>
              {workouts.exercises.map((e) => (
                <tr key={e.exercise}>
                  <td style={styles.td}>{e.exercise}</td>
                  <td style={styles.tdNum}>{e.sessions}</td>
                  <td style={styles.tdNum}>{e.reps}</td>
                  <td style={styles.tdNum}>{percent(e.good_form_reps, e.reps)}</td>
                  <td style={styles.tdNum}>{e.points}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3 style={styles.subTitle}>Recent sessions</h3>
          <div style={{ ...styles.tabList, paddingLeft: 0, marginTop: 0 }}>
            {workouts.recent.map((w) => (
              <div key={w.time} style={styles.tabItem}>
                <span style={styles.tabTitle}>
                  {formatWhen(w.time)} · {w.exercise}
                  {w.completed ? "" : " (stopped early)"}
                </span>
                <span style={styles.tabSeconds}>
                  {w.reps}/{w.target_reps} reps · {w.good_form_reps} good form · +{w.points}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div style={styles.stat}>
      <div style={styles.statValue}>{value}</div>
      <div style={styles.statLabel}>{label}</div>
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
  titleIcon: {
    verticalAlign: "-3px",
    marginRight: 8,
  },
  subTitle: {
    margin: "24px 0 8px",
    fontSize: 15,
    opacity: 0.85,
  },
  statRow: {
    display: "grid",
    gridTemplateColumns: "repeat(3, 1fr)",
    gap: 12,
  },
  stat: {
    background: "#1a1a2e",
    borderRadius: 8,
    padding: "12px 14px",
  },
  statValue: {
    fontSize: 24,
    fontWeight: 600,
  },
  statLabel: {
    fontSize: 12,
    textTransform: "uppercase",
    letterSpacing: 0.5,
    opacity: 0.7,
    marginTop: 2,
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: 14,
  },
  th: {
    textAlign: "left",
    fontWeight: 600,
    opacity: 0.7,
    padding: "6px 8px 6px 0",
    borderBottom: "1px solid #33334d",
  },
  thNum: {
    textAlign: "right",
    fontWeight: 600,
    opacity: 0.7,
    padding: "6px 0 6px 8px",
    borderBottom: "1px solid #33334d",
  },
  td: {
    textAlign: "left",
    padding: "8px 8px 8px 0",
    borderBottom: "1px solid #33334d",
  },
  tdNum: {
    textAlign: "right",
    padding: "8px 0 8px 8px",
    borderBottom: "1px solid #33334d",
    fontVariantNumeric: "tabular-nums",
  },
  tooltip: {
    background: "#1a1a2e",
    border: "1px solid #33334d",
    borderRadius: 8,
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
