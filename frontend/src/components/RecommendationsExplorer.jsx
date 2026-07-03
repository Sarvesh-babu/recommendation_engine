import { useEffect, useState } from "react";
import { getPersonalized, getFrequentlyBoughtTogether, getPopular, listCustomers, listProducts } from "../api";

const TABS = [
  { key: "personalized", label: "Personalized" },
  { key: "fbt", label: "Frequently bought together" },
  { key: "popular", label: "Popular" },
];

export default function RecommendationsExplorer({ runId }) {
  const [tab, setTab] = useState("personalized");
  const [input, setInput] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [customers, setCustomers] = useState([]);
  const [products, setProducts] = useState([]);

  useEffect(() => {
    listCustomers(runId).then((d) => setCustomers(d.customers)).catch(() => setCustomers([]));
    listProducts(runId).then((d) => setProducts(d.products)).catch(() => setProducts([]));
  }, [runId]);

  // Lets the user type a name (shown in the datalist) but resolves it back
  // to the id the API actually expects.
  function resolveId(value, options, idKey) {
    const trimmed = value.trim();
    const match = options.find((o) => o.name === trimmed || o[idKey] === trimmed);
    return match ? match[idKey] : trimmed;
  }

  async function handleLookup(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    setResult(null);
    try {
      let data;
      if (tab === "personalized") data = await getPersonalized(resolveId(input, customers, "customer_id"), runId);
      else if (tab === "fbt") data = await getFrequentlyBoughtTogether(resolveId(input, products, "product_id"), runId);
      else data = await getPopular(input.trim() || null, runId);
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const placeholder =
    tab === "personalized" ? "Search customer by name" : tab === "fbt" ? "Search product by name" : "segment (optional)";
  const datalistOptions = tab === "personalized" ? customers : tab === "fbt" ? products : [];
  const datalistIdKey = tab === "personalized" ? "customer_id" : "product_id";

  return (
    <div className="space-y-4">
      <div className="flex gap-1 rounded-md bg-slate-100 p-1 border border-sky-100">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => {
              setTab(t.key);
              setResult(null);
              setError(null);
              setInput("");
            }}
            className={`flex-1 text-xs px-2 py-1.5 rounded ${
              tab === t.key ? "bg-white text-sky-700 shadow-sm" : "text-slate-500 hover:text-slate-800"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <form onSubmit={handleLookup} className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={placeholder}
          list="recommendations-explorer-options"
          className="flex-1 rounded-md bg-white border border-sky-200 px-3 py-2 text-sm text-slate-900 shadow-sm focus:outline-none focus:ring-2 focus:ring-sky-300"
        />
        <datalist id="recommendations-explorer-options">
          {datalistOptions.map((o) => (
            <option key={o[datalistIdKey]} value={o.name} />
          ))}
        </datalist>
        <button
          type="submit"
          disabled={loading || (tab !== "popular" && !input.trim())}
          className="rounded-md bg-sky-600 hover:bg-sky-500 disabled:opacity-40 px-4 py-2 text-sm font-medium text-white shadow-sm"
        >
          {loading ? "..." : "Look up"}
        </button>
      </form>

      {error && <p className="text-sm text-rose-600">{error}</p>}

      {result && (
        <div className="rounded-md border border-sky-100 bg-white/80 p-3 space-y-2 shadow-sm">
          <p className="text-xs text-slate-500">
            {result.customer_name && <>for {result.customer_name} · </>}
            {result.product_name && <>frequently bought with {result.product_name} · </>}
            run {result.run_id} · computed at {result.computed_at}
            {result.source && <> · source: {result.source}</>}
          </p>
          {result.recommendations.length === 0 ? (
            <p className="text-sm text-slate-500">No recommendations found.</p>
          ) : (
            <ol className="space-y-1 text-sm">
              {result.recommendations.map((item, idx) => (
                <li
                  key={item.product_id || item}
                  className="rounded bg-slate-50 px-2 py-1.5 border border-slate-100 flex items-baseline gap-2"
                >
                  <span className="text-sky-600">{idx + 1}.</span>
                  <span className="flex-1">
                    <span className="font-medium text-slate-800">{item.name || item}</span>
                    {item.reason && <span className="block text-xs text-slate-500">{item.reason}</span>}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}
