import { useState, useEffect } from "react";

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

  if (!data) return <p>Connecting to Kurou Pet...</p>;

  return (
    <div>
      <h1>Kurou Pet Dashboard</h1>
      <p>Affection Points: {data.total_affection_points}</p>
      <p>Happiness Count: {data.total_happiness_count}</p>
      <p>Anger Count: {data.total_anger_count}</p>
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </div>
  );
}

export default App;
