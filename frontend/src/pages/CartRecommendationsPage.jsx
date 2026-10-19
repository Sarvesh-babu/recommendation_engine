import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getCartRecommendations, getSampleCarts, listProducts } from "../api";

/* ─────────────────── Helper Components ─────────────────── */
function KpiCard({ label, value, sub, variant = "sky" }) {
  const bg = {
    sky: "bg-sky-50/60 border-sky-200/60",
    emerald: "bg-emerald-50/60 border-emerald-200/60",
    amber: "bg-amber-50/60 border-amber-200/60",
    violet: "bg-violet-50/60 border-violet-200/60",
    rose: "bg-rose-50/60 border-rose-200/60",
  }[variant] || "bg-sky-50/60 border-sky-200/60";

  const text = {
    sky: "text-sky-700",
    emerald: "text-emerald-700",
    amber: "text-amber-700",
    violet: "text-violet-700",
    rose: "text-rose-700",
  }[variant] || "text-sky-700";

  return (
    <div className={`${bg} border rounded-xl px-4 py-3 flex flex-col gap-0.5 min-w-[140px]`}>
      <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{label}</span>
      <span className={`text-xl font-bold ${text}`}>{value}</span>
      {sub && <span className="text-[11px] text-slate-500">{sub}</span>}
    </div>
  );
}

function Badge({ children, variant = "sky" }) {
  const cls = {
    sky: "bg-sky-100 text-sky-700 border border-sky-200",
    emerald: "bg-emerald-100 text-emerald-700 border border-emerald-200",
    amber: "bg-amber-100 text-amber-700 border border-amber-200",
    rose: "bg-rose-100 text-rose-700 border border-rose-200",
    violet: "bg-violet-100 text-violet-700 border border-violet-200",
  }[variant] || "bg-sky-100 text-sky-700 border border-sky-200";

  return (
    <span className={`${cls} text-[10px] font-semibold px-2 py-0.5 rounded-md uppercase tracking-wide`}>
      {children}
    </span>
  );
}

const fmt = (v, digits, suffix = "", prefix = "") => (v == null ? "—" : `${prefix}${Number(v).toFixed(digits)}${suffix}`);

const TIER_BADGE = {
  "Strong Association": "emerald",
  "Positive Association": "sky",
  "Weak Evidence": "amber",
  "No co-purchase history": "rose",
  "Insufficient history": "rose",
};

const THRESHOLD_SOURCE = {
  optimizer: "recommended by the Promotion Optimizer for this run",
  spec_default: "spec default (the optimizer found no threshold that pays back)",
  request: "set on the request",
};

function evidenceText(ev) {
  if (!ev) return null;
  if (!ev.sufficient) return "No historical basket contains these cart items, so confidence and lift can't be measured.";
  const basis = ev.basis === "full_cart"
    ? "baskets containing the full cart"
    : `baskets containing any cart item (only ${ev.full_cart_baskets} contained the full cart)`;
  return `Confidence and lift are based on ${ev.cart_baskets.toLocaleString()} of ${ev.total_baskets.toLocaleString()} ${basis}.`;
}

/* ───────────────────────── MAIN PAGE ───────────────────────── */
export default function CartRecommendationsPage() {
  const { runId } = useParams();
  const [products, setProducts] = useState([]);
  const [searchInput, setSearchInput] = useState("");
  const [customerLabel, setCustomerLabel] = useState("");
  const [cartItems, setCartItems] = useState([]);
  const [sampleCarts, setSampleCarts] = useState([]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    listProducts(runId).then((d) => setProducts(d.products)).catch(() => setProducts([]));
    getSampleCarts(runId, 3).then((d) => setSampleCarts(d.carts)).catch(() => setSampleCarts([]));
  }, [runId]);

  function loadSampleCart(sample) {
    setCartItems(sample.cart);
    setCustomerLabel(sample.customer_label);
    setResult(null);
  }

  function resolveId(value, options, idKey) {
    const trimmed = value.trim();
    const match = options.find((o) => o.name === trimmed || o[idKey] === trimmed);
    return match ? match[idKey] : null;
  }

  function addToCart(e) {
    e.preventDefault();
    const productId = resolveId(searchInput, products, "product_id");
    if (!productId) return;
    setCartItems((items) => {
      if (items.some((i) => i.product_id === productId)) return items;
      const match = products.find((p) => p.product_id === productId);
      return [...items, { product_id: productId, name: match?.name || productId }];
    });
    setSearchInput("");
  }

  function removeFromCart(productId) {
    setCartItems((items) => items.filter((i) => i.product_id !== productId));
  }

  async function handleRecommend() {
    setError(null);
    setLoading(true);
    setResult(null);
    try {
      const data = await getCartRecommendations(
        cartItems.map((i) => i.product_id),
        runId,
        customerLabel.trim() || null
      );
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const ins = result?.insights || {};
  const hasInsights = Object.keys(ins).length > 0;

  return (
    <div className="min-h-screen text-slate-900 bg-slate-50/50">
      {/* ─── HEADER ─── */}
      <header className="border-b border-slate-200 bg-white px-6 py-4 shadow-sm sticky top-0 z-20">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-slate-900">
              Cart Companion Recommendations & Insights
            </h1>
            <p className="text-xs text-slate-500">
              Build a cart and evaluate automated cross-sell strategies with financial impact analysis.
            </p>
          </div>
          {runId && <span className="text-xs text-slate-400 font-mono">Run: {runId}</span>}
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8 space-y-6">
        {/* ─── SAMPLE CARTS ─── */}
        {sampleCarts.length > 0 && (
          <section className="space-y-2">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-600">
              Quick Load — Sample Customer Carts
            </h2>
            <div className="flex flex-wrap gap-2">
              {sampleCarts.map((sample) => (
                <button
                  key={sample.customer_id}
                  onClick={() => loadSampleCart(sample)}
                  className="rounded-lg border border-slate-200 bg-white hover:bg-slate-50 px-3.5 py-2 text-xs text-slate-700 shadow-sm transition-all"
                >
                  <span className="font-semibold text-slate-900">{sample.customer_label}</span>
                  <span className="ml-1.5 text-slate-500">({sample.cart.length} item{sample.cart.length === 1 ? "" : "s"})</span>
                </button>
              ))}
            </div>
          </section>
        )}

        {/* ─── CART BUILDER ─── */}
        <section className="rounded-xl border border-slate-200 bg-white shadow-sm p-5 space-y-4">
          <div className="space-y-1.5">
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-600">Customer (optional)</label>
            <input
              value={customerLabel}
              onChange={(e) => setCustomerLabel(e.target.value)}
              placeholder="e.g. Customer X"
              className="w-full rounded-lg bg-white border border-slate-300 px-3 py-2 text-sm text-slate-900 shadow-sm focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500 transition-all"
            />
          </div>

          <form onSubmit={addToCart} className="space-y-1.5">
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-600">Add products to cart</label>
            <div className="flex gap-2">
              <input
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Search product by name…"
                list="cart-product-options"
                className="flex-1 rounded-lg bg-white border border-slate-300 px-3 py-2 text-sm text-slate-900 shadow-sm focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500 transition-all"
              />
              <datalist id="cart-product-options">
                {products.map((p) => (
                  <option key={p.product_id} value={p.name} />
                ))}
              </datalist>
              <button
                type="submit"
                disabled={!searchInput.trim()}
                className="rounded-lg bg-sky-700 hover:bg-sky-800 disabled:opacity-40 px-4 py-2 text-sm font-medium text-white shadow-sm transition-all"
              >
                + Add
              </button>
            </div>
          </form>

          {/* Cart items */}
          <div className="space-y-2">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-600">
              Active Cart ({cartItems.length} {cartItems.length === 1 ? "item" : "items"})
            </h2>
            {cartItems.length === 0 ? (
              <p className="text-sm text-slate-400 italic">No items added. Search above or select a sample cart.</p>
            ) : (
              <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white overflow-hidden">
                {cartItems.map((item) => (
                  <li key={item.product_id} className="flex items-center justify-between px-3.5 py-2.5 text-sm hover:bg-slate-50 transition-colors">
                    <span className="text-slate-800 font-medium">{item.name}</span>
                    <button
                      onClick={() => removeFromCart(item.product_id)}
                      className="text-xs text-rose-600 hover:text-rose-700 font-medium transition-colors"
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <button
            onClick={handleRecommend}
            disabled={loading || cartItems.length === 0}
            className="w-full rounded-lg bg-sky-800 hover:bg-sky-900 disabled:opacity-40 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all"
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Computing Recommendations & Insights…
              </span>
            ) : (
              "Generate Recommendations & Insights"
            )}
          </button>
        </section>

        {error && (
          <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 font-medium">
            Error: {error}
          </div>
        )}

        {/* ─── RESULTS WITH INSIGHTS ─── */}
        {result && (
          <div className="space-y-6 animate-in">
            {/* Meta info */}
            <p className="text-xs text-slate-500">
              {result.customer_label && <>Customer: <span className="font-semibold text-slate-700">{result.customer_label}</span> · </>}
              Run ID: <span className="font-mono text-slate-700">{result.run_id}</span>
              {result.computed_at && (
                <> · Computed at {
                  !isNaN(Number(result.computed_at))
                    ? new Date(Number(result.computed_at) * 1000).toLocaleTimeString()
                    : new Date(result.computed_at).toLocaleTimeString()
                }</>
              )}
            </p>

            {/* ──── EXECUTIVE NARRATIVE BANNER ──── */}
            {ins.narrative_summary && (
              <div className="rounded-xl border border-violet-200 bg-violet-50/60 p-4 shadow-sm">
                <h3 className="text-xs font-bold uppercase tracking-wider text-violet-800 mb-1">Executive Decision Summary</h3>
                <p className="text-sm text-slate-700 leading-relaxed">{ins.narrative_summary}</p>
              </div>
            )}

            {/* ──── KPI CARDS ──── */}
            {hasInsights && (
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                <KpiCard
                  label="Cart Total"
                  value={`$${ins.current_cart_total?.toFixed(2) ?? "—"}`}
                  sub="Current value"
                  variant="sky"
                />
                <KpiCard
                  label="Projected Total"
                  value={`$${ins.projected_cart_total?.toFixed(2) ?? "—"}`}
                  sub="After top addition"
                  variant="emerald"
                />
                <KpiCard
                  label="Revenue Uplift"
                  value={fmt(ins.revenue_lift_pct, 1, "%", "+")}
                  sub="vs. current cart"
                  variant="amber"
                />
                <KpiCard
                  label="Top Confidence"
                  value={fmt(ins.top_confidence_score_pct, 1, "%")}
                  sub="P(top item | cart)"
                  variant="violet"
                />
                <KpiCard
                  label="Lift Factor"
                  value={fmt(ins.top_lift_factor, 2, "x")}
                  sub={ins.top_lift_factor == null ? "no basket history" : ins.top_significant ? "significant (q < 0.05)" : "not significant"}
                  variant="rose"
                />
              </div>
            )}
            {hasInsights && (
              <p className="text-xs text-slate-500 -mt-3">
                {evidenceText(ins.evidence)}
                {ins.prices_imputed?.length > 0 && ` Prices for ${ins.prices_imputed.length} item(s) were missing and use the dataset average.`}
              </p>
            )}

            {/* ──── SHIPPING NUDGE ──── */}
            {hasInsights && !ins.shipping_nudge && ins.qualifies_for_free_shipping && (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 px-4 py-3 text-sm text-slate-700 shadow-sm">
                This cart already qualifies for free shipping (threshold ${ins.free_shipping_threshold?.toFixed(2)},{" "}
                {THRESHOLD_SOURCE[ins.free_shipping_threshold_source]}).
              </div>
            )}
            {ins.shipping_nudge && (
              <div
                className={`rounded-xl border p-4 shadow-sm space-y-2 ${
                  ins.shipping_nudge.reaches_threshold ? "border-emerald-200 bg-emerald-50/60" : "border-amber-200 bg-amber-50/60"
                }`}
              >
                <h3 className={`text-xs font-bold uppercase tracking-wider ${ins.shipping_nudge.reaches_threshold ? "text-emerald-800" : "text-amber-800"}`}>
                  Free Shipping Nudge Strategy
                </h3>
                <p className="text-sm text-slate-700">{ins.shipping_nudge.nudge_message}</p>
                <p className="text-[11px] text-slate-500">
                  Threshold ${ins.shipping_nudge.threshold.toFixed(2)}: {THRESHOLD_SOURCE[ins.free_shipping_threshold_source]}.
                </p>
                <div className="flex items-center gap-3">
                  <div className="flex-1 bg-emerald-200/50 rounded-full h-2 overflow-hidden">
                    <div
                      className="bg-emerald-600 h-full rounded-full transition-all duration-500"
                      style={{ width: `${Math.min(100, (ins.shipping_nudge.current_total / ins.shipping_nudge.threshold) * 100)}%` }}
                    />
                  </div>
                  <span className="text-xs font-semibold text-emerald-800">
                    ${ins.shipping_nudge.amount_needed?.toFixed(2)} remaining
                  </span>
                </div>
              </div>
            )}

            {/* ──── BUNDLE STRATEGY ──── */}
            {ins.bundle_strategy && (
              <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-4 shadow-sm">
                <h3 className="text-xs font-bold uppercase tracking-wider text-amber-800 mb-1">Smart Bundle Strategy</h3>
                <p className="text-sm font-semibold text-slate-800">{ins.bundle_strategy.bundle_headline}</p>
                <div className="flex flex-wrap gap-4 mt-2 text-xs text-slate-600">
                  <span>Bundle price: <strong className="text-amber-900">${ins.bundle_strategy.bundle_combo_price}</strong></span>
                  <span>Customer savings: <strong className="text-emerald-700">${ins.bundle_strategy.savings_amount}</strong></span>
                  {ins.bundle_strategy.is_cross_category && (
                    <Badge variant="violet">Cross-category: {ins.bundle_strategy.new_category}</Badge>
                  )}
                </div>
              </div>
            )}

            {/* ──── ENRICHED RECOMMENDATION CARDS ──── */}
            <section className="space-y-3">
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-600">
                Recommended Companion Products
              </h2>
              {result.recommendations.length === 0 ? (
                <p className="text-sm text-slate-500 italic">No companion recommendations found for this cart.</p>
              ) : (
                <div className="space-y-2">
                  {result.recommendations.map((item, idx) => (
                    <div
                      key={item.product_id}
                      className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm hover:border-slate-300 transition-all"
                    >
                      <div className="flex items-start gap-3">
                        <div className="w-7 h-7 rounded-md bg-slate-100 flex items-center justify-center text-xs font-bold text-slate-700 border border-slate-200 shrink-0">
                          #{idx + 1}
                        </div>

                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-semibold text-slate-900">{item.name}</span>
                            {item.price != null && (
                              <span className="text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded">
                                ${item.price.toFixed(2)}
                              </span>
                            )}
                            {item.category && item.category !== "General" && (
                              <Badge variant="sky">{item.category}</Badge>
                            )}
                            {item.association_tier && (
                              <Badge variant={TIER_BADGE[item.association_tier] || "amber"}>{item.association_tier}</Badge>
                            )}
                          </div>
                          {item.reason && (
                            <p className="text-xs text-slate-500 mt-1">{item.reason}</p>
                          )}
                          {(item.confidence_score_pct != null || item.lift_factor != null) && (
                            <div className="flex items-center gap-4 mt-2">
                              {item.confidence_score_pct != null && (
                                <div className="flex items-center gap-2 text-xs">
                                  <span className="text-slate-500">Confidence:</span>
                                  <div className="w-24 bg-slate-100 rounded-full h-1.5 overflow-hidden border border-slate-200">
                                    <div
                                      className="bg-sky-600 h-full rounded-full transition-all duration-500"
                                      style={{ width: `${Math.min(100, item.confidence_score_pct)}%` }}
                                    />
                                  </div>
                                  <span className="font-semibold text-slate-800">{item.confidence_score_pct}%</span>
                                </div>
                              )}
                              {item.lift_factor != null && (
                                <span className="text-xs text-slate-500">
                                  Lift: <strong className="text-slate-800">{item.lift_factor}x</strong>
                                </span>
                              )}
                              {item.cooccurrence_baskets != null && ins.evidence?.sufficient && (
                                <span className="text-xs text-slate-500">
                                  {item.cooccurrence_baskets} of {ins.evidence.cart_baskets} cart baskets
                                  {item.q_value != null && <> · q = {item.q_value < 0.001 ? "<0.001" : item.q_value}</>}
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* ──── REVENUE LIFT SUMMARY TABLE ──── */}
            {hasInsights && (
              <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm space-y-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600">
                  Revenue Impact Summary
                </h3>
                <table className="w-full text-sm">
                  <tbody className="divide-y divide-slate-100">
                    <tr className="hover:bg-slate-50">
                      <td className="py-2 text-slate-600">Current Cart Value</td>
                      <td className="py-2 text-right font-semibold text-slate-800">${ins.current_cart_total?.toFixed(2)}</td>
                    </tr>
                    <tr className="hover:bg-slate-50">
                      <td className="py-2 text-slate-600">Top Recommendation Price</td>
                      <td className="py-2 text-right font-semibold text-sky-700">${ins.top_recommendation_price?.toFixed(2)}</td>
                    </tr>
                    <tr className="hover:bg-slate-50">
                      <td className="py-2 text-slate-600">Projected Cart (with top add)</td>
                      <td className="py-2 text-right font-semibold text-emerald-700">${ins.projected_cart_total?.toFixed(2)}</td>
                    </tr>
                    <tr className="hover:bg-slate-50">
                      <td className="py-2 text-slate-600">Total Revenue Lift Potential (top 3 recommendations, if all are added)</td>
                      <td className="py-2 text-right font-semibold text-amber-700">${ins.potential_revenue_lift?.toFixed(2)}</td>
                    </tr>
                    <tr className="hover:bg-slate-50">
                      <td className="py-2 text-slate-600">Expected Revenue Lift (top 3, Σ confidence × price)</td>
                      <td className="py-2 text-right font-semibold text-amber-700">${ins.expected_revenue_lift?.toFixed(2)}</td>
                    </tr>
                    <tr className="bg-slate-50">
                      <td className="py-2.5 text-slate-800 font-bold">Revenue Uplift %</td>
                      <td className="py-2.5 text-right font-bold text-violet-800">{fmt(ins.revenue_lift_pct, 1, "%", "+")}</td>
                    </tr>
                  </tbody>
                </table>
              </section>
            )}
          </div>
        )}
      </main>

      <style>{`
        .animate-in {
          animation: fadeSlideIn 0.3s ease-out both;
        }
        @keyframes fadeSlideIn {
          from { opacity: 0; transform: translateY(8px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}
