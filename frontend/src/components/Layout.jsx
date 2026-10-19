import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import ganitLogo from "../assets/ganit-logo.png";

const NAV_ITEMS = [
  {
    label: "Home",
    description: "What this app does and which recommendation models are available.",
    path: () => "/",
    needsRun: false,
  },
  {
    label: "Upload",
    description: "Upload your transactions, customers, and products (plus optional sessions, returns, search logs, and promotions), and validate the schema.",
    path: () => "/upload",
    needsRun: false,
  },
  {
    label: "AI Refinement (Layer 1)",
    description: "Autonomous data profiling, 6 canonical category classification, AST-audited rules & feature engineering powered by Qwen 3.8-27B.",
    path: (runId) => `/layer1/${runId}`,
    needsRun: true,
  },

  {
    label: "Review data (EDA)",
    description: "Inspect distributions and data quality across all uploaded files before training starts.",
    path: (runId) => `/eda/${runId}`,
    needsRun: true,
  },
  {
    label: "Model settings",
    description: "Choose which algorithm runs for personalized, frequently-bought-together, and popular recommendations before training.",
    path: (runId) => `/models/${runId}`,
    needsRun: true,
  },
  {
    label: "Results",
    description: "Browse personalized recommendations produced by the trained models for this run.",
    path: (runId) => `/results/${runId}`,
    needsRun: true,
  },
  {
    label: "Cart recommendations",
    description: "Pick a set of cart items and get companion-product recommendations based on this run's purchase co-occurrence.",
    path: (runId) => `/cart/${runId}`,
    needsRun: true,
  },
  {
    label: "Validation",
    description: "Offline precision/recall/hit-rate@k metrics, compared against a popularity baseline.",
    path: (runId) => `/validation/${runId}`,
    needsRun: true,
  },
  {
    label: "Insights",
    description: "Merchandising insights: category cross-sell heatmap, revenue opportunity sizing, product affinity network, action cards, promotion & threshold optimizer, and seasonal trend detection.",
    path: (runId) => `/insights/${runId}`,
    needsRun: true,
  },
];

function currentRunId(pathname) {
  const match = pathname.match(/^\/(?:layer1|eda|models|results|validation|cart|insights)\/([^/]+)/);
  return match ? match[1] : null;
}


export default function Layout({ children }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(false);
  const runId = currentRunId(location.pathname);

  return (
    <div className="min-h-screen flex">
      <aside
        className={`shrink-0 border-r border-sky-100/80 bg-white/70 backdrop-blur transition-all ${
          collapsed ? "w-12" : "w-64"
        }`}
      >
        <div className="flex items-center justify-between px-3 py-4">
          {!collapsed && <img src={ganitLogo} alt="Ganit" className="h-7 w-auto" />}
          <button
            onClick={() => setCollapsed((c) => !c)}
            className="text-slate-400 hover:text-slate-600 text-sm px-1"
            aria-label="Toggle menu"
            title={collapsed ? "Expand menu" : "Collapse menu"}
          >
            {collapsed ? "»" : "«"}
          </button>
        </div>

        {!collapsed && (
          <nav className="px-3 space-y-1.5 pb-6">
            {NAV_ITEMS.map((item) => {
              const disabled = item.needsRun && !runId;
              const target = item.path(runId);
              const active =
                target === "/"
                  ? location.pathname === "/"
                  : location.pathname.startsWith(target.split("/").slice(0, 2).join("/"));
              return (
                <div key={item.label} className="group relative">
                  <button
                    disabled={disabled}
                    onClick={() => navigate(target)}
                    className={`w-full text-left rounded-md px-3 py-2 text-sm transition ${
                      disabled
                        ? "text-slate-300 cursor-not-allowed"
                        : active
                        ? "bg-sky-100 text-sky-800 font-medium"
                        : "text-slate-600 hover:bg-sky-50 hover:text-sky-700"
                    }`}
                  >
                    {item.label}
                  </button>
                  <div className="pointer-events-none absolute left-full top-0 ml-2 w-56 rounded-md bg-slate-800 text-white text-xs px-3 py-2 opacity-0 group-hover:opacity-100 transition z-10 shadow-lg">
                    {item.description}
                    {disabled && <p className="mt-1 text-slate-300">Start an upload run to unlock this page.</p>}
                  </div>
                </div>
              );
            })}
          </nav>
        )}
      </aside>

      <div className="flex-1 min-w-0">{children}</div>
    </div>
  );
}
