import { useState } from "react";
import {
  BarChart,
  Bar,
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

// Curated Harmonious Palette (Sky Blue, Cyan, Indigo, Emerald, Amber, Violet)
const HARMONIOUS_PIE_COLORS = ["#0284c7", "#06b6d4", "#6366f1", "#10b981", "#f59e0b", "#8b5cf6", "#ec4899"];

/* ──────────────────────── heatmap helpers ──────────────────────── */
const HEAT_BLUE  = { r: 59, g: 130, b: 246 };
const HEAT_WHITE = { r: 248, g: 250, b: 252 };
const HEAT_RED   = { r: 239, g: 68,  b: 68  };

function heatmapColor(val) {
  const t = (val + 1) / 2;
  const low  = t < 0.5 ? HEAT_BLUE  : HEAT_WHITE;
  const high = t < 0.5 ? HEAT_WHITE : HEAT_RED;
  const f = t < 0.5 ? t * 2 : (t - 0.5) * 2;
  const r = Math.round(low.r + (high.r - low.r) * f);
  const g = Math.round(low.g + (high.g - low.g) * f);
  const b = Math.round(low.b + (high.b - low.b) * f);
  return `rgb(${r},${g},${b})`;
}

export default function EdaCharts({ eda }) {
  const [activeTab, setActiveTab] = useState("overview");
  const [tableSubTab, setTableSubTab] = useState("retained");

  const TABS = [
    { key: "overview",              label: "Overview" },
    { key: "feature_distributions", label: "Distributions" },
    { key: "correlations",          label: "Correlations" },
    { key: "feature_table",         label: "Feature Table" },
  ];

  return (
    <div className="space-y-6 font-sans">
      {/* Top Metric Summary Cards */}
      <SummaryStats eda={eda} />

      {/* Overview Insights Banner */}
      {eda.insights?.overview && activeTab === "overview" && (
        <InsightsBanner insights={eda.insights.overview} title="Key Dataset Insights" variant="indigo" />
      )}

      {/* Tab Navigation */}
      <div className="flex flex-wrap items-center gap-2 border-b border-sky-100 pb-2">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2 rounded-md text-xs font-semibold uppercase tracking-wider transition flex items-center gap-2 ${
              activeTab === tab.key
                ? "bg-gradient-to-r from-sky-600 to-indigo-600 text-white shadow-sm"
                : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-50"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ══════════ OVERVIEW TAB ══════════ */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          {/* Executive Overview KPI Cards */}
          <OverviewKPIs eda={eda} />

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <ChartCard title="Transactions by Category">
              {eda.category_breakdown && eda.category_breakdown.length > 0 ? (
                <ResponsiveContainer width="100%" height={290}>
                  <PieChart>
                    <Pie data={eda.category_breakdown} dataKey="count" nameKey="category" cx="50%" cy="45%" outerRadius={95} label={({ category }) => category}>
                      {eda.category_breakdown.map((_, i) => (
                        <Cell key={i} fill={HARMONIOUS_PIE_COLORS[i % HARMONIOUS_PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: "6px" }} />
                    <Legend wrapperStyle={{ fontSize: 12, paddingTop: "10px" }} />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-[250px] flex items-center justify-center text-xs text-slate-400 italic">
                  Category breakdown available when product categories are provided.
                </div>
              )}
            </ChartCard>

            <ChartCard title="Transactions by Customer Segment">
              {eda.segment_breakdown && eda.segment_breakdown.length > 0 ? (
                <ResponsiveContainer width="100%" height={290}>
                  <PieChart>
                    <Pie data={eda.segment_breakdown} dataKey="count" nameKey="segment" cx="50%" cy="45%" outerRadius={95} label={({ segment }) => segment}>
                      {eda.segment_breakdown.map((_, i) => (
                        <Cell key={i} fill={HARMONIOUS_PIE_COLORS[(i + 2) % HARMONIOUS_PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: "6px" }} />
                    <Legend wrapperStyle={{ fontSize: 12, paddingTop: "10px" }} />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-[250px] flex items-center justify-center text-xs text-slate-400 italic">
                  Segment breakdown available when customer segments are provided.
                </div>
              )}
            </ChartCard>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <ChartCard title="Top Products by Transaction Count">
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={eda.top_products || []} margin={{ top: 10, right: 10, left: 10, bottom: 25 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="product_id" stroke="#64748b" tick={{ fontSize: 11 }} label={{ value: "Product Identifier", position: "insideBottom", offset: -15, style: { fontSize: 11, fill: "#64748b" } }} />
                  <YAxis stroke="#64748b" tick={{ fontSize: 11 }} label={{ value: "Transaction Count", angle: -90, position: "insideLeft", style: { fontSize: 11, fill: "#64748b" } }} />
                  <Tooltip contentStyle={{ background: "#fff", border: "1px solid #e2e8f0" }} />
                  <Bar dataKey="count" fill="#0284c7" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard title="Weekly Transaction Volume Trend">
              <ResponsiveContainer width="100%" height={260}>
                <AreaChart data={eda.transactions_over_time || []} margin={{ top: 10, right: 10, left: 10, bottom: 25 }}>
                  <defs>
                    <linearGradient id="colorTime" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.8}/>
                      <stop offset="95%" stopColor="#06b6d4" stopOpacity={0.0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="period" stroke="#64748b" tick={{ fontSize: 10 }} label={{ value: "Timeline Period", position: "insideBottom", offset: -15, style: { fontSize: 11, fill: "#64748b" } }} />
                  <YAxis stroke="#64748b" tick={{ fontSize: 11 }} label={{ value: "Volume", angle: -90, position: "insideLeft", style: { fontSize: 11, fill: "#64748b" } }} />
                  <Tooltip contentStyle={{ background: "#fff", border: "1px solid #e2e8f0" }} />
                  <Area type="monotone" dataKey="count" stroke="#06b6d4" fillOpacity={1} fill="url(#colorTime)" />
                </AreaChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>
        </div>
      )}

      {/* ══════════ FEATURE DISTRIBUTIONS TAB ══════════ */}
      {activeTab === "feature_distributions" && (
        <DistributionTab eda={eda} />
      )}

      {/* ══════════ CORRELATION HEATMAP TAB ══════════ */}
      {activeTab === "correlations" && (
        <CorrelationTab eda={eda} />
      )}

      {/* ══════════ FEATURE TABLE TAB ══════════ */}
      {activeTab === "feature_table" && eda.column_stats?.length > 0 && (() => {
        const retainedFeatures = eda.column_stats.filter((col) => col.status === "retained");
        const droppedFeatures = eda.column_stats.filter((col) => col.status === "dropped");
        const displayedFeatures = tableSubTab === "retained" ? retainedFeatures : droppedFeatures;

        return (
          <div className="rounded-md border border-sky-100 bg-white p-4 shadow-sm space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 pb-3">
              <div>
                <h3 className="text-xs font-semibold text-slate-700 uppercase tracking-wider">
                  Feature Quality Map & Modeling Audit
                </h3>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  Categorized view of features retained for modeling vs. dropped due to skewness, zero-variance, or correlation redundancy.
                </p>
              </div>

              <div className="flex items-center bg-slate-100 p-1 rounded-md text-xs font-semibold">
                <button
                  onClick={() => setTableSubTab("retained")}
                  className={`px-3 py-1 rounded transition flex items-center gap-1.5 ${
                    tableSubTab === "retained"
                      ? "bg-emerald-600 text-white shadow-sm"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  <span>Retained for Modeling</span>
                  <span className={`px-1.5 py-0.2 rounded-full text-[10px] ${tableSubTab === "retained" ? "bg-emerald-700 text-white" : "bg-slate-200 text-slate-700"}`}>
                    {retainedFeatures.length}
                  </span>
                </button>
                <button
                  onClick={() => setTableSubTab("dropped")}
                  className={`px-3 py-1 rounded transition flex items-center gap-1.5 ${
                    tableSubTab === "dropped"
                      ? "bg-rose-600 text-white shadow-sm"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  <span>Filtered / Dropped</span>
                  <span className={`px-1.5 py-0.2 rounded-full text-[10px] ${tableSubTab === "dropped" ? "bg-rose-700 text-white" : "bg-slate-200 text-slate-700"}`}>
                    {droppedFeatures.length}
                  </span>
                </button>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-700">
                <thead className="bg-sky-50/70 text-slate-600 uppercase border-b border-sky-100 font-semibold">
                  <tr>
                    <th className="p-2.5">Dataset</th>
                    <th className="p-2.5">Column Name</th>
                    <th className="p-2.5">Type</th>
                    <th className="p-2.5">Lineage</th>
                    <th className="p-2.5">Unique</th>
                    <th className="p-2.5">Nulls</th>
                    <th className="p-2.5">Skewness</th>
                    {tableSubTab === "retained" ? (
                      <th className="p-2.5">Action Suggestion / Status</th>
                    ) : (
                      <th className="p-2.5">Filter / Drop Reason</th>
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {displayedFeatures.map((col, idx) => (
                    <tr key={idx} className="hover:bg-sky-50/30">
                      <td className="p-2.5 text-slate-400 text-[11px] font-bold">{col.dataset}</td>
                      <td className="p-2.5 font-semibold text-slate-900 flex items-center gap-1.5">
                        {col.column_name}
                        {col.is_key && (
                          <span className="bg-amber-100 text-amber-800 text-[9px] px-1.5 py-0.5 rounded font-medium">KEY</span>
                        )}
                      </td>
                      <td className="p-2.5">
                        <span className="bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded text-[10px]">{col.dtype}</span>
                      </td>
                      <td className="p-2.5">
                        {col.is_engineered ? (
                          <span className="bg-indigo-50 text-indigo-700 border border-indigo-200 px-1.5 py-0.5 rounded text-[10px] font-medium">
                            {col.lineage ? col.lineage.replace(/_/g, " ") : "engineered"}
                          </span>
                        ) : (
                          <span className="bg-slate-50 text-slate-500 border border-slate-200 px-1.5 py-0.5 rounded text-[10px]">
                            raw
                          </span>
                        )}
                      </td>
                      <td className="p-2.5 font-medium">{col.unique_count}</td>
                      <td className="p-2.5">{col.null_count === 0 ? <span className="text-emerald-600 font-semibold">0</span> : <span className="text-amber-600">{col.null_count}</span>}</td>
                      <td className="p-2.5 font-medium">{col.skewness !== undefined ? <span className={Math.abs(col.skewness) > 1.0 ? "text-amber-600 font-bold" : "text-emerald-600"}>{col.skewness}</span> : "-"}</td>
                      {tableSubTab === "retained" ? (
                        <td className="p-2.5 text-[11px] text-emerald-700 bg-emerald-50/50 rounded font-medium">
                          {col.action_suggestion || "Retained for modeling & EDA analysis"}
                        </td>
                      ) : (
                        <td className="p-2.5 text-[11px]">
                          <span className="inline-block bg-rose-50 text-rose-800 border border-rose-200 px-2 py-0.5 rounded font-medium">
                            {col.drop_reason || col.action_suggestion}
                          </span>
                        </td>
                      )}
                    </tr>
                  ))}
                  {displayedFeatures.length === 0 && (
                    <tr>
                      <td colSpan={8} className="p-6 text-center text-slate-400 italic">
                        No features found in this category.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        );
      })()}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════
   OVERVIEW KPIS COMPONENT
   ══════════════════════════════════════════════════════════════════ */
function OverviewKPIs({ eda }) {
  const stats = eda.overview_stats || {};
  
  const kpis = [
    { label: "Retained Features", value: stats.n_retained_features ?? (eda.column_stats ? eda.column_stats.filter(c => c.status === "retained").length : "—"), desc: "Selected for modeling & analysis", color: "text-indigo-700" },
    { label: "Filtered Features", value: stats.n_dropped_features ?? (eda.column_stats ? eda.column_stats.filter(c => c.status === "dropped").length : "—"), desc: "Collinear or zero variance", color: "text-rose-700" },
    { label: "Engineered Lineage", value: stats.n_engineered_features != null ? `${stats.n_engineered_features} features` : "Layer 1 active", desc: "Derived behavioral metrics", color: "text-sky-700" },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {kpis.map((kpi, i) => (
        <div key={i} className="rounded-lg border border-slate-200 bg-white p-3.5 shadow-sm hover:border-sky-300 transition">
          <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">{kpi.label}</p>
          <p className={`text-xl font-bold mt-1 ${kpi.color}`}>{kpi.value}</p>
          <p className="text-[11px] text-slate-400 mt-1">{kpi.desc}</p>
        </div>
      ))}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════
   DISTRIBUTION TAB — interactive feature selector + stats + mini grid
   ══════════════════════════════════════════════════════════════════ */
function DistributionTab({ eda }) {
  const distData = eda.numeric_distributions || {};
  const featureNames = Object.keys(distData);
  const [selectedFeature, setSelectedFeature] = useState(featureNames[0] || "");

  const getDistBins = (feat) => {
    const val = distData[feat];
    if (!val) return [];
    return Array.isArray(val) ? val : (val.bins || []);
  };

  const getDistStats = (feat) => {
    const val = distData[feat];
    if (!val || Array.isArray(val)) return null;
    return val;
  };

  const selectedBins = getDistBins(selectedFeature);
  const selectedStats = getDistStats(selectedFeature);

  if (!featureNames.length) {
    return (
      <div className="p-12 text-center text-slate-400 bg-white rounded-lg border border-slate-200">
        No numerical feature distributions available.
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Distribution Insights Banner */}
      {eda.insights?.distribution && (
        <InsightsBanner insights={eda.insights.distribution} title="Distribution Insights & Skewness Analysis" variant="emerald" />
      )}

      {/* Feature selector pills */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-bold text-slate-500 uppercase tracking-wider mr-1">Select Feature:</span>
        {featureNames.map((feat) => (
          <button
            key={feat}
            onClick={() => setSelectedFeature(feat)}
            className={`px-3.5 py-1.5 rounded-full text-xs font-semibold transition-all ${
              selectedFeature === feat
                ? "bg-gradient-to-r from-indigo-600 to-sky-600 text-white shadow-sm"
                : "bg-white text-slate-600 border border-slate-200 hover:border-indigo-300 hover:bg-indigo-50"
            }`}
          >
            {feat}
          </button>
        ))}
      </div>

      {/* Selected feature detail card */}
      {selectedFeature && (
        <ChartCard title={`Distribution Histogram: ${selectedFeature.toUpperCase()}`}>
          {/* Stats row */}
          {selectedStats && (
            <div className="flex flex-wrap gap-3 mb-4 pt-1">
              <StatPill label="Mean" value={selectedStats.mean} />
              <StatPill label="Median" value={selectedStats.median} />
              <StatPill label="Std Dev" value={selectedStats.std} />
              <StatPill label="Skewness" value={selectedStats.skewness} highlight={Math.abs(selectedStats.skewness || 0) > 1.0} />
              <StatPill label="Min Value" value={selectedStats.min} />
              <StatPill label="Max Value" value={selectedStats.max} />
            </div>
          )}
          
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={selectedBins} barCategoryGap={2} margin={{ top: 10, right: 20, left: 15, bottom: 45 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis 
                dataKey="range" 
                stroke="#64748b" 
                tick={{ fontSize: 10 }} 
                angle={-25} 
                textAnchor="end" 
                interval={0}
                label={{ value: `${selectedFeature} Value Bins`, position: "insideBottom", offset: -35, style: { fontSize: 12, fill: "#475569", fontWeight: 600 } }} 
              />
              <YAxis 
                stroke="#64748b" 
                tick={{ fontSize: 11 }}
                label={{ value: "Frequency Count", angle: -90, position: "insideLeft", style: { fontSize: 12, fill: "#475569", fontWeight: 600 } }} 
              />
              <Tooltip
                contentStyle={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: "8px", boxShadow: "0 4px 12px rgba(0,0,0,0.08)" }}
                formatter={(value) => [value, "Frequency Count"]}
                labelFormatter={(label) => `Range Bin: ${label}`}
              />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {selectedBins.map((_, i) => (
                  <Cell key={i} fill={`hsl(${225 + i * 8}, 70%, ${50 + i * 2}%)`} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      )}

      {/* Mini grid of all distributions */}
      {featureNames.length > 1 && (
        <div className="pt-2">
          <h4 className="text-xs font-semibold text-slate-600 uppercase tracking-wider mb-3">All Retained Feature Distributions</h4>
          <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
            {featureNames.map((feat) => {
              const bins = getDistBins(feat);
              const stats = getDistStats(feat);
              return (
                <div
                  key={feat}
                  onClick={() => setSelectedFeature(feat)}
                  className={`rounded-lg border p-3 cursor-pointer transition-all hover:shadow-md ${
                    selectedFeature === feat
                      ? "border-indigo-400 bg-indigo-50/30 shadow-sm"
                      : "border-slate-200 bg-white hover:border-sky-300"
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-semibold text-slate-800">{feat}</span>
                    {stats && (
                      <span className={`text-[10px] font-medium px-2 py-0.5 rounded ${
                        Math.abs(stats.skewness || 0) > 1.0
                          ? "bg-amber-100 text-amber-800"
                          : "bg-emerald-100 text-emerald-700"
                      }`}>
                        skew: {stats.skewness}
                      </span>
                    )}
                  </div>
                  <ResponsiveContainer width="100%" height={80}>
                    <BarChart data={bins} barCategoryGap={0}>
                      <Bar dataKey="count" fill={selectedFeature === feat ? "#6366f1" : "#94a3b8"} radius={[2, 2, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════
   CORRELATION TAB — interactive heatmap with fully visible feature labels
   ══════════════════════════════════════════════════════════════════ */
function CorrelationTab({ eda }) {
  const corrData = eda.correlation_matrix || {};
  const columns = corrData.columns || [];
  const matrix = corrData.matrix || [];
  const [hoveredCell, setHoveredCell] = useState(null);

  if (!columns.length || !matrix.length) {
    return (
      <div className="p-12 text-center text-slate-400 bg-white rounded-lg border border-slate-200">
        No correlation matrix available. Requires at least 2 retained numeric features.
      </div>
    );
  }

  // Label width increased to 200px so full feature names (e.g. customer_txn_freq) are completely visible
  const labelWidth = 200;
  const cellSize = columns.length <= 6 ? 64 : columns.length <= 10 ? 54 : 44;
  const headerHeight = 110;

  return (
    <div className="space-y-5">
      {eda.insights?.correlation && (
        <InsightsBanner insights={eda.insights.correlation} title="Correlation Insights & Multicollinearity Audit" variant="sky" />
      )}

      <ChartCard title="Cross-Feature Pearson Correlation Matrix (Collinearity Check)">
        <div className="overflow-x-auto py-4">
          <div style={{ display: "inline-block", position: "relative", minWidth: labelWidth + columns.length * cellSize + 40 }}>
            {/* Column headers (rotated cleanly without clipping) */}
            <div style={{ display: "flex", marginLeft: labelWidth, height: headerHeight, position: "relative" }}>
              {columns.map((col) => (
                <div
                  key={col}
                  style={{
                    width: cellSize,
                    position: "relative",
                  }}
                >
                  <span
                    style={{
                      position: "absolute",
                      bottom: 8,
                      left: cellSize / 2 - 8,
                      transform: "rotate(-45deg)",
                      transformOrigin: "left bottom",
                      whiteSpace: "nowrap",
                      fontSize: 11,
                      fontWeight: 600,
                      color: "#475569",
                    }}
                  >
                    {col}
                  </span>
                </div>
              ))}
            </div>

            {/* Heatmap rows */}
            {columns.map((rowCol, rIdx) => (
              <div key={rowCol} style={{ display: "flex", alignItems: "center" }}>
                {/* Row label - 200px width ensures complete feature name visibility */}
                <div
                  style={{
                    width: labelWidth,
                    textAlign: "right",
                    paddingRight: 12,
                    fontSize: 11,
                    fontWeight: 600,
                    color: "#475569",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                  title={rowCol}
                >
                  {rowCol}
                </div>
                {/* Heatmap Cells */}
                {columns.map((colCol, cIdx) => {
                  const val = matrix[rIdx]?.[cIdx] ?? 0;
                  const isHovered = hoveredCell?.row === rIdx && hoveredCell?.col === cIdx;
                  const isSelf = rIdx === cIdx;
                  return (
                    <div
                      key={colCol}
                      style={{
                        width: cellSize,
                        height: cellSize,
                        backgroundColor: isSelf ? "#e2e8f0" : heatmapColor(val),
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontSize: cellSize < 50 ? 10 : 11,
                        fontWeight: isHovered ? 700 : isSelf ? 700 : 600,
                        color: isSelf ? "#334155" : Math.abs(val) > 0.55 ? "#ffffff" : "#1e293b",
                        cursor: "pointer",
                        border: isHovered ? "2px solid #0f172a" : "1px solid rgba(255,255,255,0.5)",
                        borderRadius: 4,
                        transition: "all 0.15s ease",
                        transform: isHovered ? "scale(1.08)" : "scale(1)",
                        zIndex: isHovered ? 10 : 1,
                        position: "relative",
                      }}
                      onMouseEnter={() => setHoveredCell({ row: rIdx, col: cIdx, val, rowCol, colCol })}
                      onMouseLeave={() => setHoveredCell(null)}
                    >
                      {val.toFixed(2)}
                    </div>
                  );
                })}
              </div>
            ))}

            {/* Hover tooltip */}
            {hoveredCell && (
              <div
                style={{
                  position: "absolute",
                  top: headerHeight,
                  right: 10,
                  background: "rgba(15,23,42,0.95)",
                  color: "#ffffff",
                  padding: "10px 14px",
                  borderRadius: 8,
                  fontSize: 12,
                  lineHeight: 1.6,
                  boxShadow: "0 4px 16px rgba(0,0,0,0.25)",
                  zIndex: 50,
                  pointerEvents: "none",
                }}
              >
                <div><strong>{hoveredCell.rowCol}</strong> ↔ <strong>{hoveredCell.colCol}</strong></div>
                <div>Correlation: <strong>r = {hoveredCell.val.toFixed(3)}</strong></div>
                <div style={{ fontSize: 11, color: "#cbd5e1" }}>
                  {Math.abs(hoveredCell.val) > 0.7
                    ? "Strong correlation (Potential redundancy)"
                    : Math.abs(hoveredCell.val) > 0.4
                    ? "Moderate correlation"
                    : "Weak correlation (Independent signal)"}
                </div>
              </div>
            )}

            {/* Legend bar */}
            <div className="flex items-center justify-center gap-3 mt-6 pt-2 border-t border-slate-100">
              <span className="text-xs font-semibold text-blue-600">Negative (-1.0)</span>
              <div
                style={{
                  width: 220,
                  height: 12,
                  borderRadius: 6,
                  background: "linear-gradient(90deg, #3b82f6, #f8fafc, #ef4444)",
                }}
              />
              <span className="text-xs font-semibold text-red-600">Positive (+1.0)</span>
            </div>
          </div>
        </div>
      </ChartCard>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════
   REUSABLE UTILITY COMPONENTS
   ══════════════════════════════════════════════════════════════════ */
function ChartCard({ title, children }) {
  return (
    <div className="rounded-lg border border-sky-100 bg-white p-4 shadow-sm space-y-2">
      <h3 className="text-xs font-semibold text-slate-700 uppercase tracking-wider">{title}</h3>
      {children}
    </div>
  );
}

function SummaryStats({ eda }) {
  const stats = [
    ["Transactions", eda.n_transactions ? eda.n_transactions.toLocaleString() : "0", "Total interaction records"],
    ["Customers", eda.n_customers ? eda.n_customers.toLocaleString() : "0", "Unique customer accounts"],
    ["Products", eda.n_products ? eda.n_products.toLocaleString() : "0", "Catalog items"],
    ["Matrix Sparsity", `${((eda.sparsity || 0) * 100).toFixed(1)}%`, "Unobserved customer-item pairs"],
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {stats.map(([label, value, desc]) => (
        <div key={label} className="rounded-lg border border-sky-200 bg-gradient-to-br from-sky-50 to-white p-3.5 shadow-sm">
          <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">{label}</p>
          <p className="text-xl font-bold text-sky-900 mt-1">{value}</p>
          <p className="text-[10px] text-slate-400 mt-1">{desc}</p>
        </div>
      ))}
    </div>
  );
}

function InsightsBanner({ insights, title, variant = "indigo" }) {
  const colorMap = {
    indigo: { border: "border-l-indigo-500", bg: "bg-indigo-50/60", title: "text-indigo-800", text: "text-indigo-900" },
    sky:    { border: "border-l-sky-500",    bg: "bg-sky-50/60",    title: "text-sky-800",    text: "text-sky-900" },
    emerald:{ border: "border-l-emerald-500",bg: "bg-emerald-50/60",title: "text-emerald-800",text: "text-emerald-900" },
    violet: { border: "border-l-violet-500", bg: "bg-violet-50/60", title: "text-violet-800", text: "text-violet-900" },
  };
  const c = colorMap[variant] || colorMap.indigo;

  return (
    <div className={`rounded-lg border-l-4 ${c.border} ${c.bg} p-4 shadow-sm`}>
      <p className={`text-[11px] font-bold uppercase tracking-wider mb-2 ${c.title}`}>{title}</p>
      <div className="space-y-1">
        {insights.map((line, i) => (
          <p key={i} className={`text-xs leading-relaxed ${c.text}`}>{line}</p>
        ))}
      </div>
    </div>
  );
}

function StatPill({ label, value, highlight }) {
  return (
    <div className={`flex flex-col items-center px-3 py-1.5 rounded-lg border text-center min-w-[75px] ${
      highlight ? "bg-amber-50 border-amber-200" : "bg-slate-50 border-slate-200"
    }`}>
      <span className="text-[9px] text-slate-500 uppercase tracking-wider font-semibold">{label}</span>
      <span className={`text-sm font-bold mt-0.5 ${highlight ? "text-amber-700" : "text-slate-900"}`}>
        {value != null ? value : "—"}
      </span>
    </div>
  );
}
