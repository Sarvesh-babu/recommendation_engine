"""Cart Companion insights against Cart_Companion_Insights_Mathematical_Specification.pdf.

The fixture reproduces the spec's worked example exactly:
  cart C = Mouse ($30) + Sleeve ($15); r1 = USB-C Hub ($25); r2 = Cleaning Kit ($10); r3 = Cable Clips ($8)
  N = 10,000 baskets, B_C = 400, B_r1 = 1,000, B_(C∩r1) = 200
Run:  python -m pytest tests/test_cart_insights_math.py -q
"""
import pandas as pd
import pytest

from app.insights.basket_index import build_basket_index
from app.pipeline.cart_insights import compute_cart_insights

PRICES = {"MOUSE": 30.0, "SLEEVE": 15.0, "HUB": 25.0, "KIT": 10.0, "CLIPS": 8.0, "FILLER": 1.0, "LONER": 40.0}
RECS = [
    {"product_id": "HUB", "name": "USB-C Multi-port Hub"},
    {"product_id": "KIT", "name": "Screen Cleaning Kit"},
    {"product_id": "CLIPS", "name": "Cable Clips"},
]


def _baskets():
    yield from [{"MOUSE", "SLEEVE", "HUB"}] * 200  # B_(C∩r1) = 200
    yield from [{"MOUSE", "SLEEVE"}] * 200         # B_C = 400
    yield from [{"HUB"}] * 800                      # B_r1 = 1,000
    yield from [{"KIT"}] * 50
    yield from [{"CLIPS"}] * 50
    yield from [{"LONER"}] * 10
    yield from [{"FILLER"}] * (10_000 - 1310)


@pytest.fixture(scope="module")
def index():
    rows = [
        {"transaction_id": f"T{i}", "customer_id": f"C{i % 500}", "product_id": p, "quantity": 1,
         "price": PRICES[p], "timestamp": "2025-01-01"}
        for i, basket in enumerate(_baskets()) for p in sorted(basket)
    ]
    products = pd.DataFrame([{"product_id": p, "name": p, "category": "c", "price": v} for p, v in PRICES.items()])
    return build_basket_index(pd.DataFrame(rows), products)


@pytest.fixture(scope="module")
def spec(index):
    return compute_cart_insights(index, ["MOUSE", "SLEEVE"], RECS, free_shipping_threshold=50.0)


def test_dataset_matches_spec_baseline(index):
    assert index.n_baskets == 10_000
    assert index.product_support["HUB"] == 1_000


def test_financials_spec_2(spec):
    assert spec["current_cart_total"] == 45.00        # 2.1
    assert spec["projected_cart_total"] == 70.00      # 2.1
    assert spec["revenue_lift_pct"] == 55.6           # 2.2
    assert spec["potential_revenue_lift"] == 43.00    # 2.3


def test_association_spec_3(spec):
    assert spec["evidence"]["basis"] == "full_cart"
    assert spec["evidence"]["cart_baskets"] == 400
    assert spec["top_confidence_score_pct"] == 50.0   # 3.1  200 / 400
    assert spec["top_lift_factor"] == 5.0             # 3.2  0.50 / 0.10
    assert spec["top_significant"] is True


def test_shipping_and_bundle_spec_4(spec):
    nudge = spec["shipping_nudge"]                    # 4.1
    assert nudge["amount_needed"] == 5.00
    assert nudge["suggested_product_id"] == "HUB"
    assert nudge["reaches_threshold"] is True
    assert nudge["nudge_message"] == (
        "Add USB-C Multi-port Hub ($25.00) to unlock FREE Shipping (Cart is $5.00 away from $50 threshold)."
    )
    bundle = spec["bundle_strategy"]                  # 4.2
    assert bundle["bundle_combo_price"] == 63.00
    assert bundle["savings_amount"] == 7.00
    assert bundle["bundle_headline"] == "Smart Bundle Combo: Save 10% when adding USB-C Multi-port Hub"


def test_items_never_cobought_report_zero_not_a_default(spec):
    kit = spec["recommendations"][1]
    assert kit["cooccurrence_baskets"] == 0
    assert kit["confidence_score_pct"] == 0.0
    assert kit["lift_factor"] == 0.0
    assert kit["association_tier"] == "No co-purchase history"
    # expected lift only credits r1: 0.50 × $25
    assert spec["expected_revenue_lift"] == 12.50


def test_no_history_returns_none_not_fabricated(index):
    out = compute_cart_insights(index, ["UNSEEN"], RECS)
    assert out["evidence"]["sufficient"] is False
    assert out["top_confidence_score_pct"] is None
    assert out["top_lift_factor"] is None
    assert out["prices_imputed"] == ["UNSEEN"]   # dataset-average price, flagged
    assert "Model-only recommendation" in out["narrative_summary"]


def test_lift_below_one_is_not_clamped(index):
    # MOUSE alone: B_C = 400, HUB in 200 of them → conf 0.5, lift 5.0; FILLER never with MOUSE → lift 0
    out = compute_cart_insights(index, ["HUB"], [{"product_id": "MOUSE", "name": "Mouse"}, {"product_id": "FILLER", "name": "Filler"}])
    assert out["recommendations"][0]["lift_factor"] == pytest.approx(round((200 / 1000) / (400 / 10_000), 2))
    assert out["recommendations"][1]["lift_factor"] == 0.0


def test_any_item_basis_when_full_cart_is_rare(index):
    out = compute_cart_insights(index, ["MOUSE", "LONER"], RECS)
    assert out["evidence"]["full_cart_baskets"] == 0
    assert out["evidence"]["basis"] == "any_item"
    assert out["evidence"]["cart_baskets"] == 410


def test_nudge_does_not_promise_free_shipping_it_cannot_deliver(index):
    out = compute_cart_insights(index, ["MOUSE", "SLEEVE"], RECS, free_shipping_threshold=200.0)
    nudge = out["shipping_nudge"]
    assert nudge["reaches_threshold"] is False
    assert "unlock" not in nudge["nudge_message"]
    assert "still leaves" in nudge["nudge_message"]


def test_nudge_uses_cheapest_pair_when_no_single_item_covers_gap(index):
    out = compute_cart_insights(index, ["MOUSE", "SLEEVE"], RECS, free_shipping_threshold=78.0)  # gap 33
    nudge = out["shipping_nudge"]
    assert nudge["reaches_threshold"] is True
    assert {p["product_id"] for p in nudge["suggested_products"]} == {"HUB", "CLIPS"}  # 25 + 8 = 33


def test_no_nudge_when_cart_already_qualifies(index):
    out = compute_cart_insights(index, ["MOUSE", "SLEEVE"], RECS, free_shipping_threshold=40.0)
    assert out["shipping_nudge"] is None
    assert out["qualifies_for_free_shipping"] is True
