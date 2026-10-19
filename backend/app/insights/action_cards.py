"""4. Auto-generated Merchandising Action Cards.

Cards are derived from the other five modules' outputs, so every number on a
card is traceable to a computed metric (shown in `metrics` and `formula`).

Priority for cards with a revenue estimate:
    impact_pct = estimated value / realised revenue × 100
    high ≥ 2%,  medium ≥ 0.5%,  low otherwise
Placement and category cards (no revenue estimate) are prioritised by lift:
    high ≥ 2.0,  medium ≥ 1.3,  low otherwise
"""
from __future__ import annotations

from typing import Any

from app.insights.basket_index import BasketIndex

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def generate_action_cards(index: BasketIndex, modules: dict[str, dict], max_cards: int = 14) -> dict[str, Any]:
    revenue = index.total_revenue
    cards: list[dict] = []
    cards += _cross_sell_cards(modules.get("revenue_opportunity", {}), revenue)
    cards += _bundle_cards(modules.get("promotion_optimizer", {}), revenue)
    cards += _shipping_card(modules.get("promotion_optimizer", {}), revenue)
    cards += _placement_cards(index, modules.get("affinity_network", {}))
    cards += _category_cards(modules.get("category_heatmap", {}))
    cards += _orphan_cards(modules.get("affinity_network", {}), revenue)
    cards += _seasonal_cards(modules.get("seasonal_trends", {}))

    cards.sort(key=lambda c: (PRIORITY_ORDER[c["priority"]], -c.get("estimated_value", 0.0)))
    cards = cards[:max_cards]
    counts: dict[str, int] = {}
    for c in cards:
        counts[c["type"]] = counts.get(c["type"], 0) + 1
    return {
        "cards": cards,
        "total_cards": len(cards),
        "by_type": counts,
    }


def _revenue_priority(value: float, revenue: float) -> str:
    pct = value / revenue * 100 if revenue else 0.0
    return "high" if pct >= 2 else "medium" if pct >= 0.5 else "low"


def _lift_priority(lift: float) -> str:
    return "high" if lift >= 2.0 else "medium" if lift >= 1.3 else "low"


def _cross_sell_cards(ro: dict, revenue: float) -> list[dict]:
    out = []
    for o in ro.get("top_opportunities", [])[:3]:
        value = o["addressable_revenue"]
        out.append({
            "type": "cross_sell_campaign",
            "priority": _revenue_priority(value, revenue),
            "title": f"Target {o['gap_customers']} {o['source_product_name']} buyers with {o['target_product_name']}",
            "description": (
                f"{o['attach_rate_pct']}% of {o['source_product_name']} buyers also buy {o['target_product_name']} "
                f"vs {o['base_rate_pct']}% of all customers (lift {o['lift']}x), but {o['gap_customers']} of "
                f"{o['source_customers']} have never bought it. Converting them at the {o['incremental_attach_pct']}% "
                f"excess attach rate is worth about {value:,.2f}."
            ),
            "estimated_value": value,
            "value_kind": "revenue",
            "metrics": {
                "gap_customers": o["gap_customers"],
                "attach_rate_pct": o["attach_rate_pct"],
                "base_rate_pct": o["base_rate_pct"],
                "incremental_attach_pct": o["incremental_attach_pct"],
                "target_price": o["target_price"],
            },
            "formula": "gap_customers × (attach − base) × target_price",
        })
    return out


def _bundle_cards(po: dict, revenue: float) -> list[dict]:
    out = []
    for p in po.get("bundle_pairs", []):
        if p["best_discount_pct"] is None:
            continue
        s = next(s for s in p["scenarios"] if s["discount_pct"] == p["best_discount_pct"])
        value = s["delta_gross_profit"]
        out.append({
            "type": "bundle_promotion",
            "priority": _revenue_priority(value, revenue),
            "title": f"Bundle {p['anchor_name']} + {p['addon_name']} at {p['best_discount_pct']}% off",
            "description": (
                f"{p['baseline_attach_pct']}% of baskets with {p['anchor_name']} already add {p['addon_name']}. "
                f"A {p['best_discount_pct']}% bundle ({s['bundle_price']:,.2f}) is projected to lift attach to "
                f"{s['attach_rate_pct']}%, adding {s['delta_revenue']:,.2f} revenue and {value:,.2f} gross profit "
                f"after {s['discount_cost']:,.2f} of discount cost."
            ),
            "estimated_value": value,
            "value_kind": "gross_profit",
            "metrics": {
                "baseline_attach_pct": p["baseline_attach_pct"],
                "promo_attach_pct": s["attach_rate_pct"],
                "bundle_price": s["bundle_price"],
                "delta_gross_profit": value,
            },
            "formula": "promo GP − baseline GP (see Promotion Optimizer)",
        })
    return out[:2]


def _shipping_card(po: dict, revenue: float) -> list[dict]:
    t = po.get("recommended_threshold")
    if t is None:
        return []
    s = next(s for s in po["shipping_scenarios"] if s["threshold"] == t)
    if not po.get("free_shipping_profitable"):
        return [{
            "type": "shipping_threshold",
            "priority": "medium",
            "title": "Free shipping does not pay back at current assumptions",
            "description": (
                f"At every simulated threshold the shipping subsidy exceeds the margin on nudged spend. "
                f"The least costly option is {t:,.2f} (net {s['net_contribution']:,.2f}). Revisit shipping cost "
                f"or margin assumptions before launching a free-shipping offer."
            ),
            "estimated_value": 0.0,
            "value_kind": None,
            "metrics": {"threshold": t, "net_contribution": s["net_contribution"]},
            "formula": "uplift × margin − (qualifying + converted) × shipping_cost",
        }]
    return [{
        "type": "shipping_threshold",
        "priority": _revenue_priority(s["net_contribution"], revenue),
        "title": f"Set the free-shipping threshold at {t:,.2f}",
        "description": (
            f"{s['qualifying_pct']}% of baskets already qualify and {s['nudgeable_carts']} carts sit within reach "
            f"(average gap {s['avg_nudge_gap']:,.2f}). Expected uplift {s['expected_uplift_revenue']:,.2f}; "
            f"net contribution after subsidy {s['net_contribution']:,.2f}."
        ),
        "estimated_value": s["net_contribution"],
        "value_kind": "net_contribution",
        "metrics": {
            "threshold": t,
            "qualifying_pct": s["qualifying_pct"],
            "nudgeable_carts": s["nudgeable_carts"],
            "net_contribution": s["net_contribution"],
        },
        "formula": "uplift × margin − (qualifying + converted) × shipping_cost",
    }]


def _placement_cards(index: BasketIndex, an: dict) -> list[dict]:
    cross = [
        e for e in an.get("edges", [])
        if index.cat(e["source"]) != index.cat(e["target"]) and e["support"] >= 3
    ]
    cross.sort(key=lambda e: (e["lift"], e["support"]), reverse=True)
    out = []
    for e in cross[:2]:
        a, b = e["source"], e["target"]
        out.append({
            "type": "placement",
            "priority": _lift_priority(e["lift"]),
            "title": f"Co-locate {index.label(a)} with {index.label(b)}",
            "description": (
                f"{index.label(a)} ({index.cat(a)}) and {index.label(b)} ({index.cat(b)}) appear together in "
                f"{e['support']} baskets — {e['lift']:.2f}x what independent buying would predict. Place them "
                f"adjacent in-store or cross-link the product pages."
            ),
            "estimated_value": 0.0,
            "value_kind": None,
            "metrics": {
                "support_baskets": e["support"],
                "lift": e["lift"],
                "confidence_a_to_b_pct": round(index.confidence(a, b) * 100, 1),
                "confidence_b_to_a_pct": round(index.confidence(b, a) * 100, 1),
            },
            "formula": "lift = n(A,B)·N / (n(A)·n(B))",
        })
    return out


def _category_cards(ch: dict) -> list[dict]:
    out = []
    for p in ch.get("strongest_pairs", [])[:1]:
        out.append({
            "type": "category_cross_promo",
            "priority": _lift_priority(p["lift"]),
            "title": f"Cross-promote {p['category_a']} and {p['category_b']}",
            "description": (
                f"Baskets mixing {p['category_a']} and {p['category_b']} occur {p['lift']:.2f}x more often than "
                f"chance ({p['count']} baskets, q = {p['q_value']}). Use shared landing pages or 'complete the look' modules."
            ),
            "estimated_value": 0.0,
            "value_kind": None,
            "metrics": {"baskets": p["count"], "lift": p["lift"]},
            "formula": "lift = n(X,Y)·N / (n(X)·n(Y))",
        })
    for p in ch.get("weakest_pairs", [])[:1]:
        out.append({
            "type": "category_cross_promo",
            "priority": "low",
            "title": f"{p['category_a']} and {p['category_b']} rarely sell together",
            "description": (
                f"Only {p['count']} baskets mix these categories ({p['lift']:.2f}x of chance, q = {p['q_value']}). Avoid spending "
                f"cross-sell slots on this pairing, or test whether it is a navigation gap."
            ),
            "estimated_value": 0.0,
            "value_kind": None,
            "metrics": {"baskets": p["count"], "lift": p["lift"]},
            "formula": "lift = n(X,Y)·N / (n(X)·n(Y))",
        })
    return out


def _orphan_cards(an: dict, revenue: float) -> list[dict]:
    out = []
    for n in an.get("orphans", [])[:2]:
        share = n["revenue"] / revenue * 100 if revenue else 0.0
        if share < 1.0:
            continue
        out.append({
            "type": "orphan_product",
            "priority": "medium" if share >= 3 else "low",
            "title": f"{n['name']} sells alone: give it companions",
            "description": (
                f"{n['name']} ({n['category']}) brings {share:.1f}% of revenue across {n['baskets']} baskets but has "
                f"no significant co-purchase partner. Test it in recommendation slots next to hub products."
            ),
            "estimated_value": 0.0,
            "value_kind": None,
            "metrics": {"revenue": n["revenue"], "revenue_share_pct": round(share, 1), "baskets": n["baskets"]},
            "formula": "degree = 0 in the affinity network",
        })
    return out


def _seasonal_cards(st: dict) -> list[dict]:
    out = []
    seasonal = [t for t in st.get("trends", []) if t["trend_type"] == "seasonal" and not t["low_expected_counts"]]
    for t in seasonal[:1]:
        out.append({
            "type": "seasonal",
            "priority": "medium",
            "title": f"Plan {t['product_a_name']} + {t['product_b_name']} around {t['peak_month']}",
            "description": (
                f"This pair's co-purchase rate peaks in {t['peak_month']} at {t['peak_index']:.0f}% of its average "
                f"month (χ² p = {t['p_value']}). Schedule the bundle or placement ahead of the peak."
            ),
            "estimated_value": 0.0,
            "value_kind": None,
            "metrics": {"peak_index": t["peak_index"], "p_value": t["p_value"], "support": t["total_support"]},
            "formula": "index_m = rate_m / mean(rate) × 100",
        })
    for c in st.get("category_trends", []):
        if c["trend"] == "stable":
            continue
        out.append({
            "type": "seasonal",
            "priority": "medium" if c["trend"] == "rising" else "low",
            "title": f"{c['category']} is {c['trend']} ({c['slope_pp_per_month']:+.2f} pp/month)",
            "description": (
                f"{c['category']} appears in {c['mean_share_pct']}% of baskets on average and the share is "
                f"{c['trend']} by {abs(c['relative_change_per_month_pct']):.1f}% per month (p = {c['p_value']}). "
                + ("Increase inventory and recommendation exposure." if c["trend"] == "rising"
                   else "Review assortment and pricing.")
            ),
            "estimated_value": 0.0,
            "value_kind": None,
            "metrics": {"slope_pp_per_month": c["slope_pp_per_month"], "r_squared": c["r_squared"], "p_value": c["p_value"]},
            "formula": "OLS slope of monthly basket share",
        })
    return out
