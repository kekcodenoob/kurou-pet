import { useState, useEffect } from "react";
// Each icon from lucide-react is its own React component you use like a custom tag,
// e.g. <Heart />. Common props: `size` (px), `color`, `strokeWidth`.
import { Heart, Smile, Angry } from "lucide-react";

function App() {
  
  const [data, setData] = useState(null);

  useEffect(() => {
    async function fetchData() {
      try {
        const response = await fetch("http://127.0.0.1:8000/");
        setData(await response.json());
      } catch (err) {
        console.error("Failed to fetch:", err);
      }
    }

    fetchData();                                      
    const interval = setInterval(fetchData, 1000);     
   
    return () => clearInterval(interval);
  }, []);

  if (!data) return <p style={styles.loading}>Connecting to Kurou Pet...</p>;

  // `Icon` here holds the *component itself* (not yet rendered).
  // We render it below with <c.Icon ... />.
  const cards = [
    { label: "Affection Points", value: data.total_affection_points, accent: "#ff6b9d", Icon: Heart },
    { label: "Happiness",        value: data.total_happiness_count,  accent: "#ffd93d", Icon: Smile },
    { label: "Anger",            value: data.total_anger_count,      accent: "#ff6b6b", Icon: Angry },
  ];

  // Object.entries({ key: value }) -> [["key", value], ...]
  // We walk every source (e.g. "YouTube"), then every tab inside its Tabs object,
  // and flatten them into one list of { source, title, seconds }.
  const tabs = Object.entries(data.source_of_anger || {})
    .flatMap(([source, info]) =>
      Object.entries(info.Tabs || {}).map(([title, seconds]) => ({
        source,
        title,
        seconds,
      }))
    )
    .sort((a, b) => b.seconds - a.seconds);

  // Max value drives the bar widths. Math.max(1, ...) avoids dividing by zero.
  const maxSeconds = Math.max(1, ...tabs.map((t) => t.seconds));

  return (
    <div style={styles.page}>
      <h1 style={styles.title}>Kurou Pet Dashboard</h1>

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
        <h2 style={styles.sectionTitle}>Time per tab</h2>
        {tabs.length === 0 ? (
          <p style={styles.empty}>No tab activity yet.</p>
        ) : (
          tabs.map((t) => (
            <div key={`${t.source}::${t.title}`} style={styles.tabRow}>
              <div style={styles.tabHeader}>
                <span style={styles.tabTitle} title={t.title}>{t.title}</span>
                <span style={styles.tabSeconds}>{t.seconds}s</span>
              </div>
              <div style={styles.tabBarTrack}>
                <div
                  style={{
                    ...styles.tabBarFill,
                    width: `${(t.seconds / maxSeconds) * 100}%`,
                  }}
                />
              </div>
              <div style={styles.tabSource}>{t.source}</div>
            </div>
          ))
        )}
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
    marginBottom: 32,
    fontSize: 32,
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
  tabRow: {
    padding: "10px 0",
    borderBottom: "1px solid #33334d",
  },
  tabHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "baseline",
    gap: 12,
    marginBottom: 6,
  },
  tabTitle: {
    fontSize: 14,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  tabSeconds: {
    fontSize: 14,
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
  tabSource: {
    fontSize: 12,
    opacity: 0.6,
    marginTop: 4,
  },
};

export default App;
