import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getCartRecommendations, getSampleCarts, listProducts } from "../api";

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
    // Today this hits a mock endpoint (`GET /recommendations/sample-carts`)
    // that returns a few real-looking carts from past purchase history.
    // Swapping in a real external cart API later means changing this one
    // call -- the rest of the page just consumes { customer_label, cart }.
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

  return (
    <div className="min-h-screen text-slate-900">
      <header className="border-b border-sky-100/80 bg-white/70 backdrop-blur px-6 py-4 shadow-sm">
        <h1 className="text-lg font-semibold">Cart recommendations</h1>
        <p className="text-sm text-slate-500">
          Build a cart and get companion-product recommendations based on this run's purchase co-occurrence.
        </p>
      </header>

      <main className="max-w-2xl mx-auto px-6 py-8 space-y-6">
        {sampleCarts.length > 0 && (
          <div className="space-y-2">
            <h2 className="text-sm font-semibold text-slate-800">Load a sample customer cart</h2>
            <p className="text-xs text-slate-500">
              Fetched from <code>GET /recommendations/sample-carts</code> -- stands in for a real cart API.
            </p>
            <div className="flex flex-wrap gap-2">
              {sampleCarts.map((sample) => (
                <button
                  key={sample.customer_id}
                  onClick={() => loadSampleCart(sample)}
                  className="rounded-md border border-sky-200 bg-white px-3 py-1.5 text-xs text-sky-700 hover:bg-sky-50 shadow-sm"
                >
                  {sample.customer_label} ({sample.cart.length} item{sample.cart.length === 1 ? "" : "s"})
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="space-y-2">
          <label className="block text-sm font-medium text-slate-700">Customer (optional, for display only)</label>
          <input
            value={customerLabel}
            onChange={(e) => setCustomerLabel(e.target.value)}
            placeholder="e.g. Customer X"
            className="w-full rounded-md bg-white border border-sky-200 px-3 py-2 text-sm text-slate-900 shadow-sm focus:outline-none focus:ring-2 focus:ring-sky-300"
          />
        </div>

        <form onSubmit={addToCart} className="space-y-2">
          <label className="block text-sm font-medium text-slate-700">Add a product to the cart</label>
          <div className="flex gap-2">
            <input
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search product by name"
              list="cart-product-options"
              className="flex-1 rounded-md bg-white border border-sky-200 px-3 py-2 text-sm text-slate-900 shadow-sm focus:outline-none focus:ring-2 focus:ring-sky-300"
            />
            <datalist id="cart-product-options">
              {products.map((p) => (
                <option key={p.product_id} value={p.name} />
              ))}
            </datalist>
            <button
              type="submit"
              disabled={!searchInput.trim()}
              className="rounded-md bg-sky-600 hover:bg-sky-500 disabled:opacity-40 px-4 py-2 text-sm font-medium text-white shadow-sm"
            >
              Add to cart
            </button>
          </div>
        </form>

        <div className="space-y-2">
          <h2 className="text-sm font-semibold text-slate-800">Cart ({cartItems.length})</h2>
          {cartItems.length === 0 ? (
            <p className="text-sm text-slate-500">No items yet -- search and add products above.</p>
          ) : (
            <ul className="divide-y divide-slate-100 rounded-md border border-sky-100 bg-white/80 shadow-sm">
              {cartItems.map((item) => (
                <li key={item.product_id} className="flex items-center justify-between px-3 py-2 text-sm">
                  <span className="text-slate-800">{item.name}</span>
                  <button
                    onClick={() => removeFromCart(item.product_id)}
                    className="text-xs text-rose-600 hover:text-rose-500"
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
          className="rounded-md bg-sky-600 hover:bg-sky-500 disabled:opacity-40 px-4 py-2 text-sm font-medium text-white shadow-sm"
        >
          {loading ? "..." : "Get recommendations"}
        </button>

        {error && <p className="text-sm text-rose-600">{error}</p>}

        {result && (
          <div className="rounded-md border border-sky-100 bg-white/80 p-3 space-y-2 shadow-sm">
            <p className="text-xs text-slate-500">
              {result.customer_label && <>for {result.customer_label} · </>}
              run {result.run_id} · computed at {result.computed_at}
            </p>
            {result.recommendations.length === 0 ? (
              <p className="text-sm text-slate-500">No recommendations found for this cart.</p>
            ) : (
              <ol className="space-y-1 text-sm">
                {result.recommendations.map((item, idx) => (
                  <li
                    key={item.product_id}
                    className="rounded bg-slate-50 px-2 py-1.5 border border-slate-100 flex items-baseline gap-2"
                  >
                    <span className="text-sky-600">{idx + 1}.</span>
                    <span className="flex-1">
                      <span className="font-medium text-slate-800">{item.name}</span>
                      {item.reason && <span className="block text-xs text-slate-500">{item.reason}</span>}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
