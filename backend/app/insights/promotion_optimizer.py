"""5. Promotion & Threshold Optimizer.

Both simulations compare a promotion against the *no-promotion baseline* over
the same historical baskets. Behavioural parameters cannot be learned from
basket data alone, so they are explicit inputs (`PromotionAssumptions`) and
are echoed back in the response.

A. Free-shipping threshold T  (basket value v = Σ quantity × unit price)
    qualifying      baskets with v ≥ T
    nudgeable       baskets with window·T ≤ v < T
    converted       nudgeable × conversion
    uplift          Σ_(nudgeable) (T − v) × conversion
                    (converted carts assumed to top up exactly to T — a lower bound)
    subsidy         (qualifying + converted) × shipping_cost
    net             uplift × gross_margin − subsidy

B. Bundle discount d on the top significant pairs (anchor A = the more
   frequent item, add-on B), over the n(A) baskets containing the anchor:
    a0              n(A,B) / n(A)                     observed attach rate
    a1              min(1, a0 · (1 + elasticity · d))  attach rate under promotion
    baseline rev    n(A) · (pA + a0·pB)
    promo rev       n(A) · (a1·(pA+pB)·(1−d) + (1−a1)·pA)
    baseline GP     n(A) · m · (pA + a0·pB)
    promo GP        n(A) · (a1·(pA+pB)·(m−d) + (1−a1)·pA·m)
    discount cost   n(A) · a1 · (pA+pB) · d   (includes baskets that would have
                                              bought both anyway — cannibalisation)
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from app.insights.basket_index import BasketIndex

THRESHOLD_QUANTILES = [0.25, 0.40, 0.50, 0.60, 0.75, 0.90]
DISCOUNT_LEVELS = [0.05, 0.10, 0.15, 0.20, 0.25]


@dataclass(frozen=True)
class PromotionAssumptions:
    nudge_window: float = 0.75       # carts within 75–100% of T can be nudged
    nudge_conversion: float = 0.30   # share of nudgeable carts that top up
    shipping_cost: float = 5.0       # cost per order shipped free
    gross_margin: float = 0.30       # gross margin on merchandise
    discount_elasticity: float = 2.0 # relative attach-rate gain per unit of discount
    bundle_pairs: int = 5            # number of top pairs to simulate bundles for


def compute_promotion_optimizer(index: BasketIndex, assumptions: PromotionAssumptions | None = None) -> dict[str, Any]:
    a = assumptions or PromotionAssumptions()
    values = index.basket_value.to_numpy(dtype=float)
    if values.size == 0:
        return {"error": "No basket data available"}

    shipping = _shipping_scenarios(values, a)
    bundles = _bundle_scenarios(index, a)

    best_shipping = max(shipping, key=lambda s: s["net_contribution"]) if shipping else None
    return {
        "assumptions": asdict(a),
        "basket_stats": {
            "total_baskets": int(values.size),
            "avg_basket_value": round(float(values.mean()), 2),
            "median_basket_value": round(float(np.median(values)), 2),
            "p25_basket_value": round(float(np.quantile(values, 0.25)), 2),
            "p75_basket_value": round(float(np.quantile(values, 0.75)), 2),
        },
        "basket_value_histogram": _histogram(values),
        "shipping_scenarios": shipping,
        "recommended_threshold": best_shipping["threshold"] if best_shipping else None,
        "free_shipping_profitable": bool(best_shipping and best_shipping["net_contribution"] > 0),
        **bundles,
    }


# ── A. free-shipping thresholds ──────────────────────────────

def _shipping_scenarios(values: np.ndarray, a: PromotionAssumptions) -> list[dict]:
    thresholds = sorted({_nice_round(float(np.quantile(values, q))) for q in THRESHOLD_QUANTILES})
    thresholds = [t for t in thresholds if t > 0]
    n = values.size
    out = []
    for t in thresholds:
        qualifying = int((values >= t).sum())
        below = values[values < t]
        nudgeable = below[below >= a.nudge_window * t]
        converted = nudgeable.size * a.nudge_conversion
        uplift = float((t - nudgeable).sum()) * a.nudge_conversion
        subsidy = (qualifying + converted) * a.shipping_cost
        net = uplift * a.gross_margin - subsidy
        out.append({
            "threshold": t,
            "qualifying_baskets": qualifying,
            "qualifying_pct": round(qualifying / n * 100, 1),
            "below_threshold_count": int(below.size),
            "avg_gap": round(float((t - below).mean()), 2) if below.size else 0.0,
            "nudgeable_carts": int(nudgeable.size),
            "avg_nudge_gap": round(float((t - nudgeable).mean()), 2) if nudgeable.size else 0.0,
            "expected_conversions": round(converted, 1),
            "expected_uplift_revenue": round(uplift, 2),
            "shipping_subsidy": round(subsidy, 2),
            "net_contribution": round(net, 2),
        })
    return out


def _nice_round(v: float) -> float:
    """Round to a price point a merchandiser would use (two significant steps of 5)."""
    if v <= 0:
        return 0.0
    step = 5 * 10 ** (math.floor(math.log10(v)) - 1)
    return float(round(round(v / step) * step, 2))


def _histogram(values: np.ndarray, bins: int = 20) -> list[dict]:
    counts, edges = np.histogram(values, bins=bins)
    return [
        {"from": round(float(edges[i]), 2), "to": round(float(edges[i + 1]), 2), "count": int(counts[i])}
        for i in range(len(counts))
    ]


# ── B. bundle discounts ──────────────────────────────────────

def _bundle_scenarios(index: BasketIndex, a: PromotionAssumptions) -> dict[str, Any]:
    pairs = []
    for (x, y), stat in index.significant_pairs()[: a.bundle_pairs]:
        anchor, addon = (x, y) if index.product_support[x] >= index.product_support[y] else (y, x)
        pairs.append(_simulate_pair(index, anchor, addon, stat.support, a))

    by_discount = []
    for i, d in enumerate(DISCOUNT_LEVELS):
        rows = [p["scenarios"][i] for p in pairs]
        delta_rev = sum(r["delta_revenue"] for r in rows)
        delta_gp = sum(r["delta_gross_profit"] for r in rows)
        by_discount.append({
            "discount_pct": round(d * 100),
            "extra_bundles": round(sum(r["extra_bundles"] for r in rows), 1),
            "discount_cost": round(sum(r["discount_cost"] for r in rows), 2),
            "delta_revenue": round(delta_rev, 2),
            "delta_gross_profit": round(delta_gp, 2),
            "profitable": delta_gp > 0,
        })

    best = max(by_discount, key=lambda s: s["delta_gross_profit"]) if by_discount else None
    return {
        "bundle_pairs": pairs,
        "bundle_scenarios": by_discount,
        "recommended_discount_pct": best["discount_pct"] if best and best["profitable"] else None,
    }


def _simulate_pair(index: BasketIndex, anchor: str, addon: str, n_ab: int, a: PromotionAssumptions) -> dict:
    n_a = index.product_support[anchor]
    p_a = index.price.get(anchor, 0.0)
    p_b = index.price.get(addon, 0.0)
    m = a.gross_margin
    a0 = n_ab / n_a
    base_rev = n_a * (p_a + a0 * p_b)
    base_gp = n_a * m * (p_a + a0 * p_b)

    scenarios = []
    for d in DISCOUNT_LEVELS:
        a1 = min(1.0, a0 * (1 + a.discount_elasticity * d))
        promo_rev = n_a * (a1 * (p_a + p_b) * (1 - d) + (1 - a1) * p_a)
        promo_gp = n_a * (a1 * (p_a + p_b) * (m - d) + (1 - a1) * p_a * m)
        scenarios.append({
            "discount_pct": round(d * 100),
            "attach_rate_pct": round(a1 * 100, 1),
            "extra_bundles": round(n_a * (a1 - a0), 2),
            "bundle_price": round((p_a + p_b) * (1 - d), 2),
            "discount_cost": round(n_a * a1 * (p_a + p_b) * d, 2),
            "delta_revenue": round(promo_rev - base_rev, 2),
            "delta_gross_profit": round(promo_gp - base_gp, 2),
        })

    best = max(scenarios, key=lambda s: s["delta_gross_profit"])
    return {
        "anchor_id": anchor,
        "anchor_name": index.label(anchor),
        "addon_id": addon,
        "addon_name": index.label(addon),
        "anchor_price": round(p_a, 2),
        "addon_price": round(p_b, 2),
        "anchor_baskets": n_a,
        "support_baskets": n_ab,
        "baseline_attach_pct": round(a0 * 100, 1),
        "lift": round(index.lift(anchor, addon), 2),
        "scenarios": scenarios,
        "best_discount_pct": best["discount_pct"] if best["delta_gross_profit"] > 0 else None,
        "best_delta_gross_profit": best["delta_gross_profit"],
    }
