import { useState, useEffect } from "react";
// Each icon from lucide-react is its own React component you use like a custom tag,
// e.g. <Heart />. Common props: `size` (px), `color`, `strokeWidth`.
import { Heart, Smile, Angry, ChevronRight } from "lucide-react";

function App() {
  const [data, setData] = useState({
    total_affection_points: 8,
    total_happiness_count: 15,
    source_of_happiness: {
      "\u2022 Pet the pet": 15,
    },
    total_anger_count: 7,
    source_of_anger: {
      "Desktop Pet": {
        "Excessive taps": 1,
      },
      YouTube: {
        "Total seconds": 75,
        Tabs: {
          "We Raced to Every Train Station in Taiwan - Ep 7 - YouTube \u2014 Firefox Developer Edition": 30,
          "The moon landing is fake, I have proof - Ep 29 - Youtube":45,
        },
      },
      Netflix: {
        "Total seconds": 100,
        Tabs: {
          "Jojo Siwa's great adventure": 23454,
          "The moon landing is fake, I have proof - Ep 29 - Youtube":23452345,
        },
      },

    },
  });

  // Tracks which source rows are expanded. Keys are source names, values are true.
  // We use an object (not just a single string) so multiple rows can be open at once.
  const [expanded, setExpanded] = useState({});
  const toggle = (source) =>
    setExpanded((prev) => ({ ...prev, [source]: !prev[source] }));

  // useEffect(() => {
  //   async function fetchData() {
  //     try {
  //       const response = await fetch("http://127.0.0.1:8000/");
  //       setData(await response.json());
  //     } catch (err) {
  //       console.error("Failed to fetch:", err);
  //     }
  //   }

  //   fetchData();
  //   const interval = setInterval(fetchData, 1000);

  //   return () => clearInterval(interval);
  // }, []);

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
