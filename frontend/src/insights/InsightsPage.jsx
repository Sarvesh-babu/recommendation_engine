import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getAllInsights } from "./insightsApi";
import ActionCards from "./components/ActionCards";
import AffinityNetwork from "./components/AffinityNetwork";
import CategoryHeatmap from "./components/CategoryHeatmap";
import PromotionOptimizer from "./components/PromotionOptimizer";
import RevenueOpportunity from "./components/RevenueOpportunity";
import SeasonalTrends from "./components/SeasonalTrends";
import { StatCard } from "./components/ui";
import { fmtMoney, fmtNum } from "./components/format";

const TABS = [
  { id: "cards", label: "Action Cards", key: "action_cards" },
  { id: "heatmap", label: "Category Heatmap", key: "category_heatmap" },
  { id: "revenue", label: "Revenue Opportunity", key: "revenue_opportunity" },
  { id: "network", label: "Affinity Network", key: "affinity_network" },
  { id: "promotion", label: "Promotion Optimizer", key: "promotion_optimizer" },
  { id: "seasonal", label: "Seasonal Trends", key: "seasonal_trends" },
];

export default function InsightsPage() {
  const { runId } = useParams();
  const [result, setResult] = useState({ runId: null, data: null, error: null });
  const [tab, setTab] = useState("cards");

  useEffect(() => {
    let cancelled = false;
    getAllInsights(runId)
      .then((data) => !cancelled && setResult({ runId, data, error: null }))
      .catch((e) => !cancelled && setResult({ runId, data: null, error: e.message }));
    return () => {
      cancelled = true;
    };
  }, [runId]);

  const loading = result.runId !== runId;
  const { data, error } = loading ? { data: null, error: null } : result;
  const ov = data?.overview;

  return (
    <div className="min-h-screen text-slate-900 bg-slate-50/50">
      <header className="border-b border-slate-200 bg-white px-6 py-4 shadow-sm sticky top-0 z-20">
        <div className="max-w-6xl mx-auto flex flex-wrap items-center justify-between gap-2">
          <div>
            <h1 className="text-lg font-bold text-slate-900">Insights</h1>
            <p className="text-xs text-slate-500">
              Merchandising insights from this run's baskets. Associations are significance-tested, so numbers you act on aren't chance.
            </p>
          </div>
          {runId && <span className="text-xs text-slate-400 font-mono">Run: {runId}</span>}
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-6 space-y-4">
        {loading && <p className="text-sm text-slate-500 py-10 text-center">Computing insights…</p>}
        {error && (
          <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 font-medium">Error: {error}</div>
        )}

        {data && !loading && (
          <>
            <div className="flex flex-wrap gap-3">
              <StatCard label="Baskets" value={fmtNum(ov.baskets)} sub={`${ov.multi_item_basket_pct}% multi-item`} />
              <StatCard label="Customers" value={fmtNum(ov.customers)} />
              <StatCard label="Products" value={fmtNum(ov.products)} sub={`${fmtNum(ov.distinct_pairs)} co-purchased pairs`} />
              <StatCard label="Revenue" value={fmtMoney(ov.revenue)} sub="Σ quantity × paid price" />
              <StatCard label="Items / basket" value={ov.avg_items_per_basket} />
            </div>

            <div className="flex gap-1 bg-white border border-slate-200 rounded-lg p-1 shadow-sm overflow-x-auto">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className={`px-4 py-2 text-xs font-semibold rounded-md transition whitespace-nowrap ${
                    tab === t.id ? "bg-slate-800 text-white shadow-sm" : "text-slate-600 hover:bg-slate-100"
                  }`}
                >
                  {t.label}
                  {data[t.key]?.error && <span className="ml-1 text-rose-400">!</span>}
                </button>
              ))}
            </div>

            <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              {tab === "cards" && <ActionCards data={data.action_cards} />}
              {tab === "heatmap" && <CategoryHeatmap data={data.category_heatmap} />}
              {tab === "revenue" && <RevenueOpportunity data={data.revenue_opportunity} />}
              {tab === "network" && <AffinityNetwork data={data.affinity_network} />}
              {tab === "promotion" && <PromotionOptimizer data={data.promotion_optimizer} runId={runId} />}
              {tab === "seasonal" && <SeasonalTrends data={data.seasonal_trends} />}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
