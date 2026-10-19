import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { getMetrics } from "../api";

const METRIC_LABELS = { precision: "Precision", recall: "Recall", hit_rate: "Hit rate" };

export default function ValidationPage() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const [metrics, setMetrics] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getMetrics(runId)
      .then(setMetrics)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [runId]);

  const chartData =
    metrics?.top_k_values.flatMap((k) =>
      Object.keys(METRIC_LABELS).map((m) => {
        const item = {
          metric: `${METRIC_LABELS[m]}@${k}`,
          "Two-Tower Neural Hybrid (v2)": metrics.model[`${m}_at_${k}`],
          "Global Bestseller Benchmark": metrics.popularity_baseline[`${m}_at_${k}`],
        };
        if (metrics.v1_baseline && metrics.v1_baseline[`${m}_at_${k}`] !== undefined) {
          item["Matrix Factorization (ALS v1)"] = metrics.v1_baseline[`${m}_at_${k}`];
        }
        return item;
      })
    ) ?? [];

  return (
    <div className="min-h-screen text-slate-900">
      <header className="border-b border-sky-100/80 bg-white/70 backdrop-blur px-6 py-4 flex items-center justify-between shadow-sm">
        <div>
          <h1 className="text-lg font-semibold">Model validation</h1>
          <p className="text-sm text-slate-500">Offline evaluation via temporal leave-out.</p>
        </div>
        <button
          onClick={() => navigate(`/results/${runId}`)}
          className="text-sm px-3 py-1.5 rounded-md bg-sky-600 text-white hover:bg-sky-500 shadow-sm"
        >
          Back to results
        </button>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-8 space-y-6">
        {loading && <p className="text-sm text-slate-500">Loading metrics...</p>}
        {metrics && (
          <>
            <p className="text-sm text-slate-500">
              Evaluated on {metrics.n_customers_evaluated} customers by holding out their most recent purchases
              and checking whether the model recommends them back.
            </p>

            {metrics.feature_provenance && (
              <FeatureProvenanceCard provenance={metrics.feature_provenance} />
            )}

            <div className="rounded-md border border-sky-100 bg-white/80 p-4 shadow-sm">
              <ResponsiveContainer width="100%" height={320}>
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#dbeafe" />
                  <XAxis dataKey="metric" stroke="#64748b" tick={{ fontSize: 11 }} />
                  <YAxis stroke="#64748b" tick={{ fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: "#ffffff", border: "1px solid #dbeafe" }} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="Two-Tower Neural Hybrid (v2)" fill="#0284c7" radius={[4, 4, 0, 0]} />
                  {metrics.v1_baseline && (
                    <Bar dataKey="Matrix Factorization (ALS v1)" fill="#6366f1" radius={[4, 4, 0, 0]} />
                  )}
                  <Bar dataKey="Global Bestseller Benchmark" fill="#94a3b8" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <MetricsTable metrics={metrics} />
          </>
        )}
      </main>
    </div>
  );
}

const FEATURE_LABELS = {
  behavioral_rfm: "Behavioral RFM",
  temporal_recency: "Temporal Recency",
  session_affinity: "Session Affinity",
  returns_adjusted_demand: "Returns-Adjusted Demand",
  search_intent: "Search Intent",
  promotion_sensitivity: "Promotion Sensitivity"
};

function FeatureProvenanceCard({ provenance }) {
  const isLayer1 = provenance.source === "LAYER1_ENGINEERED_FEATURE_STORE";
  const dims = provenance.side_feature_dims || {};

  return (
    <div className="rounded-md border border-sky-100 bg-white/80 p-4 shadow-sm space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-800 flex items-center gap-2">
          <span>Model Architecture & Provenance Diagnostics</span>
          <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-sky-100 text-sky-800">
            v2.0 (Neural Hybrid)
          </span>
        </h3>
        <span
          className={`text-xs px-2.5 py-1 rounded-full font-medium ${
            isLayer1
              ? "bg-emerald-100 text-emerald-800 border border-emerald-200"
              : "bg-amber-100 text-amber-800 border border-amber-200"
          }`}
        >
          {isLayer1 ? "✓ Feature Store Direct" : "⚠ Local Computed Fallback"}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-1 text-xs">
        <div className="p-3 rounded bg-slate-50 border border-slate-100">
          <p className="text-slate-500 font-medium">Interaction Recency Weighting</p>
          <p className="text-sm font-semibold text-slate-800 mt-0.5">
            {provenance.implicit_matrix_decay_active ? "✓ Temporal Half-Life Decay (λ=0.005)" : "Flat Weighting"}
          </p>
        </div>
        <div className="p-3 rounded bg-slate-50 border border-slate-100">
          <p className="text-slate-500 font-medium">User Dense Attributes</p>
          <p className="text-sm font-semibold text-slate-800 mt-0.5">
            {dims.customer_features_count ?? 0} Dense Features
          </p>
        </div>
        <div className="p-3 rounded bg-slate-50 border border-slate-100">
          <p className="text-slate-500 font-medium">Item Dense Attributes</p>
          <p className="text-sm font-semibold text-slate-800 mt-0.5">
            {dims.product_features_count ?? 0} Dense Features
          </p>
        </div>
      </div>

      {provenance.performance_guard?.status_message && (
        <div
          className={`p-2.5 rounded text-xs border font-medium ${
            provenance.performance_guard.fallback_triggered
              ? "bg-amber-50 text-amber-900 border-amber-200"
              : "bg-emerald-50 text-emerald-900 border-emerald-200"
          }`}
        >
          {provenance.performance_guard.status_message}
        </div>
      )}

      {provenance.features_applied && provenance.features_applied.length > 0 && (
        <div className="text-xs text-slate-500 pt-1">
          <span className="font-medium text-slate-700">Active Feature Pipelines: </span>
          {provenance.features_applied.map(f => FEATURE_LABELS[f] || f).join(" · ")}
        </div>
      )}
    </div>
  );
}

function MetricsTable({ metrics }) {
  return (
    <div className="rounded-md border border-sky-100 bg-white/80 p-4 shadow-sm overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-slate-500">
            <th className="py-1 pr-4">Metric</th>
            <th className="py-1 pr-4 font-semibold text-sky-700">Two-Tower Neural Hybrid (v2)</th>
            {metrics.v1_baseline && <th className="py-1 pr-4 font-medium text-indigo-600">Matrix Factorization (ALS v1)</th>}
            <th className="py-1 font-normal text-slate-600">Global Bestseller Benchmark</th>
          </tr>
        </thead>
        <tbody>
          {metrics.top_k_values.flatMap((k) =>
            Object.keys(METRIC_LABELS).map((m) => (
              <tr key={`${m}_${k}`} className="border-t border-slate-100">
                <td className="py-1 pr-4 text-slate-700">
                  {METRIC_LABELS[m]}@{k}
                </td>
                <td className="py-1 pr-4 font-semibold text-sky-700">
                  {metrics.model[`${m}_at_${k}`]?.toFixed(3)}
                </td>
                {metrics.v1_baseline && (
                  <td className="py-1 pr-4 font-medium text-indigo-600">
                    {metrics.v1_baseline[`${m}_at_${k}`]?.toFixed(3)}
                  </td>
                )}
                <td className="py-1 text-slate-600">{metrics.popularity_baseline[`${m}_at_${k}`]?.toFixed(3)}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
