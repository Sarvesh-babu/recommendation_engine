"""2. Revenue Opportunity Sizing.

Evaluated for every directional rule A → B whose pair is a statistically
significant positive association (BH q < alpha, see basket_index):

    C(A)            customers who bought A;  U = all customers
    C(A,B)          customers who bought both A and B (at any time)
    attach(A→B)     |C(A,B)| / |C(A)|           customer-level attach rate
    base(B)         |C(B)| / |U|                 adoption of B among all customers
    incremental     attach − base                 adoption explained by owning A
    gap(A→B)        |C(A)| − |C(A,B)|            A-buyers who have never bought B
    addressable     gap × incremental × price(B)

i.e. the expected revenue if A-buyers who have not yet bought B adopt it at
the *excess* rate their peers show over the general population. Customers who
already buy B are excluded (no realised revenue counted as opportunity) and
base adoption is subtracted (no credit for purchases that would happen anyway).

Both directions of a pair are evaluated — they target different audiences.
"""
from __future__ import annotations

from typing import Any

from app.insights.basket_index import BasketIndex


def compute_revenue_opportunity(index: BasketIndex, top_n: int = 20, alpha: float = 0.05) -> dict[str, Any]:
    significant = index.significant_pairs(alpha)
    opportunities = []
    for (a, b), stat in significant:
        for src, tgt in ((a, b), (b, a)):
            opp = _directional(index, src, tgt, stat, index.n_customers)
            if opp:
                opportunities.append(opp)

    opportunities.sort(key=lambda o: o["addressable_revenue"], reverse=True)
    top = opportunities[:top_n]
    total_all = sum(o["addressable_revenue"] for o in opportunities)
    total_top = sum(o["addressable_revenue"] for o in top)

    return {
        "top_opportunities": top,
        "total_addressable_revenue": round(total_top, 2),
        "total_addressable_revenue_all": round(total_all, 2),
        "realised_revenue": round(index.total_revenue, 2),
        "addressable_pct_of_revenue": round(total_top / index.total_revenue * 100, 2) if index.total_revenue else 0.0,
        "rules_with_opportunity": len(opportunities),
        "significant_pairs": len(significant),
        "pairs_tested": len(index.pair_stats),
        "alpha": alpha,
    }


def _directional(index: BasketIndex, src: str, tgt: str, stat, n_customers: int) -> dict | None:
    buyers_src = index.product_customers.get(src, set())
    buyers_tgt = index.product_customers.get(tgt, set())
    if not buyers_src or not n_customers:
        return None
    adopters = buyers_src & buyers_tgt
    attach = len(adopters) / len(buyers_src)
    base = len(buyers_tgt) / n_customers
    incremental = attach - base
    gap = len(buyers_src) - len(adopters)
    if gap == 0 or incremental <= 0:
        return None
    target_price = index.price.get(tgt, 0.0)
    expected_conversions = gap * incremental
    return {
        "source_product_id": src,
        "source_product_name": index.label(src),
        "target_product_id": tgt,
        "target_product_name": index.label(tgt),
        "support_baskets": stat.support,
        "basket_confidence_pct": round(index.confidence(src, tgt) * 100, 1),
        "lift": round(stat.lift, 2),
        "q_value": float(f"{stat.q_value:.3g}"),
        "source_customers": len(buyers_src),
        "already_adopted": len(adopters),
        "gap_customers": gap,
        "attach_rate_pct": round(attach * 100, 1),
        "base_rate_pct": round(base * 100, 1),
        "incremental_attach_pct": round(incremental * 100, 1),
        "expected_conversions": round(expected_conversions, 2),
        "target_price": round(target_price, 2),
        "addressable_revenue": round(expected_conversions * target_price, 2),
    }
