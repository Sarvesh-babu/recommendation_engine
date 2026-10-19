"""Math verification for the Insights layer.

Each test recomputes a published number from first principles with an
independent code path (raw pandas / scipy) and compares it with the layer's
output. Run:  python -m pytest tests/test_insights_math.py -q
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from app.insights.action_cards import generate_action_cards
from app.insights.affinity_network import compute_affinity_network
from app.insights.basket_index import bh_adjust, build_basket_index, confidence, lift
from app.insights.category_heatmap import compute_category_heatmap
from app.insights.promotion_optimizer import PromotionAssumptions, compute_promotion_optimizer
from app.insights.revenue_opportunity import compute_revenue_opportunity
from app.insights.seasonal_trends import compute_seasonal_trends

DATA = Path(__file__).resolve().parent.parent / "data" / "sample" / "retail"


@pytest.fixture(scope="module")
def raw():
    txn = pd.read_csv(DATA / "transactions.csv", dtype={"transaction_id": str, "product_id": str, "customer_id": str})
    products = pd.read_csv(DATA / "products.csv", dtype={"product_id": str})
    return txn, products


@pytest.fixture(scope="module")
def index(raw):
    return build_basket_index(*raw)


def baskets_with(txn, *pids):
    sets = txn.groupby("transaction_id")["product_id"].apply(set)
    return int(sum(all(p in s for p in pids) for s in sets))


# ── helpers against textbook values ─────────────────────────

def test_lift_and_confidence_match_spec_worked_example():
    # Cart Companion spec §3: N=10,000, B_C=400, B_r1=1,000, B_(C∩r1)=200
    assert confidence(200, 400) == pytest.approx(0.50)
    assert lift(200, 400, 1000, 10_000) == pytest.approx(5.0)


def test_bh_matches_reference_procedure():
    p = np.array([0.01, 0.04, 0.03, 0.005, 0.20])
    # sorted: .005 .01 .03 .04 .20 → ×m/rank: .025 .025 .05 .05 .20 → step-up min
    expected = np.array([0.025, 0.05, 0.05, 0.025, 0.20])
    assert bh_adjust(p) == pytest.approx(expected)


def test_pair_p_value_equals_one_sided_fisher(index, raw):
    (a, b), s = index.significant_pairs()[0]
    n, na, nb, nab = index.n_baskets, index.product_support[a], index.product_support[b], s.support
    table = [[nab, na - nab], [nb - nab, n - na - nb + nab]]
    _, fisher_p = stats.fisher_exact(table, alternative="greater")
    assert s.p_value == pytest.approx(fisher_p, rel=1e-6)


# ── basket index ────────────────────────────────────────────

def test_supports_match_raw_counts(index, raw):
    txn, _ = raw
    assert index.n_baskets == txn["transaction_id"].nunique()
    (a, b), s = index.significant_pairs()[0]
    assert index.product_support[a] == baskets_with(txn, a)
    assert s.support == baskets_with(txn, a, b)
    assert s.lift == pytest.approx(s.support * index.n_baskets / (baskets_with(txn, a) * baskets_with(txn, b)))


def test_basket_value_uses_paid_price(index, raw):
    txn, _ = raw
    expected = (txn["quantity"] * txn["price"]).groupby(txn["transaction_id"]).sum()
    assert index.basket_value.sort_index().to_numpy() == pytest.approx(expected.sort_index().to_numpy())
    assert index.total_revenue == pytest.approx(float((txn["quantity"] * txn["price"]).sum()))


# ── 1. category heatmap ─────────────────────────────────────

def test_category_cells(index, raw):
    txn, products = raw
    hm = compute_category_heatmap(index)
    cat = products.set_index("product_id")["category"]
    bc = txn.assign(c=txn["product_id"].map(cat)).groupby("transaction_id")["c"].apply(set)
    n = len(bc)
    for cell in hm["cells"]:
        if cell["row"] == cell["col"]:
            assert cell["lift"] is None
            continue
        nx = sum(cell["row"] in s for s in bc)
        ny = sum(cell["col"] in s for s in bc)
        nxy = sum(cell["row"] in s and cell["col"] in s for s in bc)
        assert cell["count"] == nxy
        assert cell["confidence_pct"] == pytest.approx(round(nxy / nx * 100, 1))
        assert cell["lift"] == pytest.approx(nxy * n / (nx * ny), abs=1e-3)
        if cell["association"] == "positive":
            assert cell["lift"] > 1 and cell["q_value"] < hm["alpha"]


# ── 2. revenue opportunity ──────────────────────────────────

def test_revenue_opportunity_rows(index, raw):
    txn, products = raw
    ro = compute_revenue_opportunity(index)
    price = products.set_index("product_id")["price"]
    custs = txn.groupby("product_id")["customer_id"].apply(set)
    n_cust = txn["customer_id"].nunique()
    for o in ro["top_opportunities"]:
        ca, cb = custs[o["source_product_id"]], custs[o["target_product_id"]]
        attach = len(ca & cb) / len(ca)
        base = len(cb) / n_cust
        gap = len(ca) - len(ca & cb)
        expected = gap * (attach - base) * price[o["target_product_id"]]
        assert o["gap_customers"] == gap
        assert o["addressable_revenue"] == pytest.approx(expected, abs=0.01)
        assert o["addressable_revenue"] > 0
    assert ro["total_addressable_revenue"] == pytest.approx(sum(o["addressable_revenue"] for o in ro["top_opportunities"]), abs=0.01)
    assert ro["total_addressable_revenue"] < ro["realised_revenue"]


# ── 3. affinity network ─────────────────────────────────────

def test_network_degrees_and_roles(index):
    net = compute_affinity_network(index)
    deg = {}
    for e in net["edges"]:
        assert e["q_value"] < 0.05 and e["lift"] > 1
        for p in (e["source"], e["target"]):
            deg[p] = deg.get(p, 0) + 1
    for n in net["nodes"]:
        assert n["degree"] == deg.get(n["product_id"], 0)
        assert 0.0 <= n["participation"] < 1.0
        assert (n["role"] == "orphan") == (n["degree"] == 0)
    assert net["summary"]["orphan_count"] == len(net["orphans"])


# ── 5. promotion optimizer ──────────────────────────────────

def test_shipping_scenarios(index):
    a = PromotionAssumptions()
    po = compute_promotion_optimizer(index, a)
    v = index.basket_value.to_numpy()
    for s in po["shipping_scenarios"]:
        t = s["threshold"]
        nudge = v[(v >= a.nudge_window * t) & (v < t)]
        qualifying = int((v >= t).sum())
        uplift = (t - nudge).sum() * a.nudge_conversion
        net = uplift * a.gross_margin - (qualifying + nudge.size * a.nudge_conversion) * a.shipping_cost
        assert s["qualifying_baskets"] == qualifying
        assert s["expected_uplift_revenue"] == pytest.approx(uplift, abs=0.01)
        assert s["net_contribution"] == pytest.approx(net, abs=0.01)
    best = max(po["shipping_scenarios"], key=lambda s: s["net_contribution"])
    assert po["recommended_threshold"] == best["threshold"]


def test_bundle_simulation_by_explicit_enumeration(index):
    """Re-derive Δrevenue by summing over individual anchor baskets."""
    a = PromotionAssumptions()
    po = compute_promotion_optimizer(index, a)
    pair = po["bundle_pairs"][0]
    A, B = pair["anchor_id"], pair["addon_id"]
    pA, pB = index.price[A], index.price[B]
    anchor_baskets = [items for items in index.baskets.values() if A in items]
    a0 = sum(B in items for items in anchor_baskets) / len(anchor_baskets)
    for s in pair["scenarios"]:
        d = s["discount_pct"] / 100
        a1 = min(1.0, a0 * (1 + a.discount_elasticity * d))
        base = sum(pA + (pB if B in items else 0) for items in anchor_baskets)
        promo = len(anchor_baskets) * (a1 * (pA + pB) * (1 - d) + (1 - a1) * pA)
        assert s["delta_revenue"] == pytest.approx(promo - base, abs=0.01)
        # At zero elasticity a discount can only give money away.
    flat = compute_promotion_optimizer(index, PromotionAssumptions(discount_elasticity=0.0))
    assert all(s["delta_revenue"] < 0 for s in flat["bundle_scenarios"])


# ── 6. seasonal trends ──────────────────────────────────────

def test_seasonal_chi_square_and_index(index, raw):
    txn, _ = raw
    st = compute_seasonal_trends(index)
    t = st["trends"][0]
    ts = txn.assign(m=pd.to_datetime(txn["timestamp"]).dt.to_period("M").astype(str))
    sets = ts.groupby("transaction_id").agg(items=("product_id", set), m=("m", "first"))
    both = sets["items"].apply(lambda s: t["product_a_id"] in s and t["product_b_id"] in s)
    obs = both.groupby(sets["m"]).sum().reindex(st["months"]).to_numpy(dtype=float)
    vol = sets.groupby("m").size().reindex(st["months"]).to_numpy(dtype=float)
    exp = obs.sum() * vol / vol.sum()
    chi2, p = stats.chisquare(obs, exp)
    assert t["chi2"] == pytest.approx(chi2, abs=1e-3)
    assert t["p_value"] == pytest.approx(p, abs=1e-4)
    rate = obs / vol
    assert t["monthly_index"][st["months"][0]] == pytest.approx(rate[0] / rate.mean() * 100, abs=0.1)


# ── 4. action cards ─────────────────────────────────────────

def test_cards_trace_back_to_modules(index):
    modules = {
        "category_heatmap": compute_category_heatmap(index),
        "revenue_opportunity": compute_revenue_opportunity(index),
        "affinity_network": compute_affinity_network(index),
        "promotion_optimizer": compute_promotion_optimizer(index),
        "seasonal_trends": compute_seasonal_trends(index),
    }
    cards = generate_action_cards(index, modules)["cards"]
    assert cards
    opp_values = {o["addressable_revenue"] for o in modules["revenue_opportunity"]["top_opportunities"]}
    for c in cards:
        if c["type"] == "cross_sell_campaign":
            assert c["estimated_value"] in opp_values
        if c["type"] == "bundle_promotion":
            assert c["estimated_value"] > 0
