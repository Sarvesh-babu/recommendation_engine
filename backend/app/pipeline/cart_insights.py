"""Cart Companion Insight Engine.

Implements Cart Companion Insights  on top of
the Insights layer's BasketIndex. No value is invented: when the data cannot
support a metric it is returned as None with the reason in `evidence`.

Notation (spec §1):  C = active cart, r = a recommended product,
N = total baskets, B_C = baskets "containing the cart", B_r = baskets with r,
B_(C∩r) = cart baskets that also contain r.

    2.1  Current_Total   = Σ P(i), i ∈ C          Projected_Total = Current_Total + P(r1)
    2.2  Uplift %        = P(r1) / Current_Total × 100
    2.3  Potential_Lift  = Σ P(r_k), k = 1..3
    3.1  Confidence %    = B_(C∩r) / B_C × 100
    3.2  Lift            = P(r | C) / P(r) = (B_(C∩r) / B_C) / (B_r / N)
    4.1  Shipping gap    = T − Current_Total
    4.2  Bundle price    = (Current_Total + P(r1)) × (1 − 0.10)

Basket basis for B_C: baskets containing the *whole* cart when there are at
least MIN_FULL_CART_BASKETS of them; otherwise baskets containing *any* cart
item (reported as basis "any_item"). One basis is used for every item so
their confidences are comparable.

Significance: B_(C∩r) is tested against independence with a one-sided
hypergeometric test, p = P(X ≥ B_(C∩r)), X ~ Hypergeom(N, B_C, B_r),
Benjamini–Hochberg adjusted across the recommendation list.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from app.insights.basket_index import UNKNOWN_CATEGORY, BasketIndex, association_p_values, bh_adjust
from app.insights.promotion_optimizer import compute_promotion_optimizer

MIN_FULL_CART_BASKETS = 5
BUNDLE_DISCOUNT_PCT = 10
SPEC_DEFAULT_SHIPPING_THRESHOLD = 50.0
ALPHA = 0.05


def recommended_shipping_threshold(index: BasketIndex) -> tuple[float, str]:
    """The Promotion Optimizer's threshold when free shipping pays back for this run, else the spec default."""
    po = compute_promotion_optimizer(index)
    if po.get("free_shipping_profitable"):
        return float(po["recommended_threshold"]), "optimizer"
    return SPEC_DEFAULT_SHIPPING_THRESHOLD, "spec_default"


def compute_cart_insights(
    index: BasketIndex,
    cart_product_ids: list[str],
    recommendations: list[dict],
    free_shipping_threshold: float = SPEC_DEFAULT_SHIPPING_THRESHOLD,
    threshold_source: str = "spec_default",
) -> dict[str, Any]:
    cart = list(dict.fromkeys(str(p) for p in cart_product_ids))
    if not cart or not recommendations or index.n_baskets == 0:
        return {}

    price, imputed = _price_lookup(index, cart + [r["product_id"] for r in recommendations])

    # ── 2. financials ───────────────────────────────────────
    current_total = sum(price[p] for p in cart)
    top = recommendations[0]
    top_id = top["product_id"]
    top_price = price[top_id]
    projected_total = current_total + top_price
    uplift_pct = top_price / current_total * 100 if current_total > 0 else None
    potential_lift = sum(price[r["product_id"]] for r in recommendations[:3])

    # ── 3. association ──────────────────────────────────────
    evidence, cart_baskets = _cart_baskets(index, cart)
    items = _item_associations(index, cart_baskets, recommendations)
    expected_lift = sum(
        (it["confidence"] or 0.0) * price[r["product_id"]] for it, r in zip(items[:3], recommendations[:3])
    )

    enriched = []
    for r, it in zip(recommendations, items):
        pid = r["product_id"]
        enriched.append({
            **r,
            "price": round(price[pid], 2),
            "price_imputed": pid in imputed,
            "category": index.cat(pid),
            "confidence_score_pct": _pct(it["confidence"]),
            "lift_factor": _round(it["lift"], 2),
            "cooccurrence_baskets": it["cooccurrence"],
            "product_baskets": index.product_support.get(pid, 0),
            "p_value": _sig(it["p_value"]),
            "q_value": _sig(it["q_value"]),
            "significant": it["significant"],
            "association_tier": it["tier"],
        })
    top_item = enriched[0]

    # ── 4. nudges & bundle ──────────────────────────────────
    shipping_nudge = _shipping_nudge(current_total, free_shipping_threshold, recommendations, price)

    cart_cats = {index.cat(p) for p in cart} - {UNKNOWN_CATEGORY}
    top_cat = index.cat(top_id)
    is_cross_category = top_cat != UNKNOWN_CATEGORY and top_cat not in cart_cats
    combined = current_total + top_price
    bundle_price = round(combined * (1 - BUNDLE_DISCOUNT_PCT / 100), 2)
    bundle_strategy = {
        "is_cross_category": is_cross_category,
        "new_category": top_cat if is_cross_category else None,
        "bundle_discount_pct": BUNDLE_DISCOUNT_PCT,
        "bundle_combo_price": bundle_price,
        "savings_amount": round(combined - bundle_price, 2),
        "bundle_headline": f"Smart Bundle Combo: Save {BUNDLE_DISCOUNT_PCT}% when adding {top.get('name', top_id)}",
    }

    return {
        "current_cart_total": round(current_total, 2),
        "projected_cart_total": round(projected_total, 2),
        "top_recommendation_price": round(top_price, 2),
        "potential_revenue_lift": round(potential_lift, 2),
        "expected_revenue_lift": round(expected_lift, 2),
        "revenue_lift_pct": _round(uplift_pct, 1),
        "top_confidence_score_pct": top_item["confidence_score_pct"],
        "top_lift_factor": top_item["lift_factor"],
        "top_significant": top_item["significant"],
        "evidence": evidence,
        "prices_imputed": sorted(imputed),
        "free_shipping_threshold": round(free_shipping_threshold, 2),
        "free_shipping_threshold_source": threshold_source,
        "qualifies_for_free_shipping": current_total >= free_shipping_threshold,
        "shipping_nudge": shipping_nudge,
        "bundle_strategy": bundle_strategy,
        "narrative_summary": _narrative(top, top_item, current_total, projected_total, uplift_pct,
                                        evidence, is_cross_category, top_cat, shipping_nudge),
        "recommendations": enriched,
    }


# ── prices ──────────────────────────────────────────────────

def _price_lookup(index: BasketIndex, pids: list[str]) -> tuple[dict[str, float], set[str]]:
    """Spec 2.1: catalogue → mean paid price (both in index.price) → dataset average."""
    known = [v for v in index.price.values() if v == v]
    average = float(np.mean(known)) if known else 0.0
    price, imputed = {}, set()
    for pid in pids:
        if pid in index.price:
            price[pid] = float(index.price[pid])
        else:
            price[pid] = average
            imputed.add(pid)
    return price, imputed


# ── association ─────────────────────────────────────────────

def _cart_baskets(index: BasketIndex, cart: list[str]) -> tuple[dict, list[frozenset]]:
    cart_set = set(cart)
    full = [b for b in index.baskets.values() if cart_set <= b]
    if len(cart) == 1 or len(full) >= MIN_FULL_CART_BASKETS:
        basis, baskets = "full_cart", full
    else:
        basis, baskets = "any_item", [b for b in index.baskets.values() if b & cart_set]
    evidence = {
        "basis": basis,
        "cart_baskets": len(baskets),
        "full_cart_baskets": len(full),
        "total_baskets": index.n_baskets,
        "min_full_cart_baskets": MIN_FULL_CART_BASKETS,
        "sufficient": len(baskets) > 0,
    }
    return evidence, baskets


def _item_associations(index: BasketIndex, cart_baskets: list[frozenset], recommendations: list[dict]) -> list[dict]:
    n, b_c = index.n_baskets, len(cart_baskets)
    co = [sum(r["product_id"] in b for b in cart_baskets) for r in recommendations]
    b_r = [index.product_support.get(r["product_id"], 0) for r in recommendations]

    if b_c == 0:
        return [{"cooccurrence": 0, "confidence": None, "lift": None, "p_value": None, "q_value": None,
                 "significant": False, "tier": "Insufficient history"} for _ in recommendations]

    p_over, _ = association_p_values(co, [b_c] * len(co), b_r, n)
    q = bh_adjust(p_over)
    out = []
    for i in range(len(recommendations)):
        conf = co[i] / b_c
        lift = conf / (b_r[i] / n) if b_r[i] else None
        significant = bool(q[i] < ALPHA and lift is not None and lift > 1)
        out.append({
            "cooccurrence": co[i],
            "confidence": conf,
            "lift": lift,
            "p_value": float(p_over[i]),
            "q_value": float(q[i]),
            "significant": significant,
            "tier": _tier(co[i], lift, significant),
        })
    return out


def _tier(cooccurrence: int, lift: float | None, significant: bool) -> str:
    if cooccurrence == 0:
        return "No co-purchase history"
    if significant and lift >= 2.0:
        return "Strong Association"
    if significant:
        return "Positive Association"
    return "Weak Evidence"


# ── shipping nudge ──────────────────────────────────────────

def _shipping_nudge(current_total: float, threshold: float, recs: list[dict], price: dict) -> dict | None:
    """Spec 4.1: first recommendation (in rank order) whose price covers the gap.
    If none does alone, the cheapest pair among the top 5 that does. If nothing
    reaches the threshold, the nudge says so instead of promising free shipping."""
    if current_total >= threshold:
        return None
    gap = threshold - current_total
    name = lambda r: r.get("name", r["product_id"])  # noqa: E731

    single = next((r for r in recs if price[r["product_id"]] >= gap), None)
    if single:
        chosen = [single]
    else:
        pool = recs[:5]
        pairs = [(a, b) for i, a in enumerate(pool) for b in pool[i + 1:]
                 if price[a["product_id"]] + price[b["product_id"]] >= gap]
        chosen = list(min(pairs, key=lambda ab: price[ab[0]["product_id"]] + price[ab[1]["product_id"]])) if pairs else [recs[0]]

    added = sum(price[r["product_id"]] for r in chosen)
    reaches = current_total + added >= threshold
    names = " + ".join(f"{name(r)} (${price[r['product_id']]:.2f})" for r in chosen)
    if reaches:
        message = (f"Add {names} to unlock FREE Shipping "
                   f"(Cart is ${gap:.2f} away from ${threshold:.0f} threshold).")
    else:
        message = (f"Cart is ${gap:.2f} away from the ${threshold:.0f} free-shipping threshold. Adding {names} "
                   f"still leaves ${threshold - current_total - added:.2f} to go.")
    return {
        "threshold": round(threshold, 2),
        "current_total": round(current_total, 2),
        "amount_needed": round(gap, 2),
        "reaches_threshold": reaches,
        "suggested_products": [{"product_id": r["product_id"], "name": name(r), "price": round(price[r["product_id"]], 2)}
                               for r in chosen],
        # single-item fields kept for existing consumers
        "suggested_product_id": chosen[0]["product_id"],
        "suggested_product_name": name(chosen[0]),
        "suggested_product_price": round(price[chosen[0]["product_id"]], 2),
        "nudge_message": message,
    }


# ── narrative ───────────────────────────────────────────────

def _narrative(top, top_item, current_total, projected_total, uplift_pct, evidence,
               is_cross_category, top_cat, shipping_nudge) -> str:
    name = top.get("name", top["product_id"])
    conf, lift = top_item["confidence_score_pct"], top_item["lift_factor"]
    if not evidence["sufficient"]:
        headline = "Model-only recommendation (no basket history for this cart)"
    elif top_item["significant"] and conf >= 60:
        headline = "High-confidence cross-sell opportunity"
    elif top_item["significant"]:
        headline = "Statistically supported cross-sell opportunity"
    else:
        headline = "Exploratory recommendation (association not statistically significant)"

    stats = f"Price: ${top_item['price']:.2f}"
    if lift is not None:
        stats += f", {conf}% confidence, lift {lift}x over baseline"
    text = f"{headline}: adding {name} ({stats}) takes the cart from ${current_total:.2f} to ${projected_total:.2f}"
    text += f" (+{uplift_pct:.1f}% revenue)." if uplift_pct is not None else "."
    if evidence["sufficient"]:
        basis = "baskets with the full cart" if evidence["basis"] == "full_cart" else "baskets with any cart item"
        text += f" Based on {evidence['cart_baskets']} historical {basis}."
    if is_cross_category:
        text += f" Expands the basket into the '{top_cat}' category."
    if shipping_nudge and shipping_nudge["reaches_threshold"] and shipping_nudge["suggested_product_id"] == top["product_id"] \
            and len(shipping_nudge["suggested_products"]) == 1:
        text += f" Also qualifies the cart for the ${shipping_nudge['threshold']:.0f} free-shipping threshold."
    return text


# ── formatting ──────────────────────────────────────────────

def _round(v: float | None, d: int) -> float | None:
    return None if v is None else round(float(v), d)


def _pct(v: float | None) -> float | None:
    return None if v is None else round(v * 100, 1)


def _sig(v: float | None) -> float | None:
    return None if v is None else float(f"{v:.3g}")
