import { useState } from "react";
import { Trends } from "./views/Trends";
import { Comparison } from "./views/Comparison";
import { Drilldown } from "./views/Drilldown";

type View = "trends" | "comparison" | "drilldown";

const VIEWS: { id: View; label: string; sub: string }[] = [
  { id: "trends", label: "Trends", sub: "Metrics over time" },
  { id: "comparison", label: "Comparison", sub: "Retrieval strategies side by side" },
  { id: "drilldown", label: "Drilldown", sub: "One question, end to end" },
];

export function App() {
  const [view, setView] = useState<View>("trends");

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">RAG · Evals</div>
        <div className="brand-sub">agent · demo</div>
        <nav className="nav">
          {VIEWS.map((v, i) => (
            <button
              key={v.id}
              className={view === v.id ? "active" : ""}
              onClick={() => setView(v.id)}
            >
              <span className="index">{String(i + 1).padStart(2, "0")}</span>
              {v.label}
            </button>
          ))}
        </nav>
      </aside>

      <main className="main">
        {view === "trends" && <Trends />}
        {view === "comparison" && <Comparison />}
        {view === "drilldown" && <Drilldown />}
      </main>
    </div>
  );
}
