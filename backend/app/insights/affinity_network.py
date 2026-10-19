"""3. Product Affinity Network Graph.

Nodes are products; an edge A–B exists only for a statistically significant
positive association (see basket_index):

    n(A,B) ≥ min_support,  lift(A,B) > 1,  BH q-value < alpha

Node metrics are computed on the full significant edge set:

    degree         k = number of edges
    strength       Σ n(A,B) over the node's edges (weighted degree)
    participation  P = 1 − Σ_c (k_c / k)²   where k_c = edges into category c
                   (Guimerà–Amaral; 0 = all partners in one category,
                   →1 = partners spread evenly across categories)

Roles (first match wins):
    hub        k ≥ max(3, 90th percentile of k among connected nodes)
    bridge     k ≥ 2 and P ≥ 0.5 and partners in ≥ 2 categories other than its own
    orphan     k = 0 — bought, but never significantly with anything
    standard   everything else

All connected nodes are returned for drawing, plus the highest-revenue orphans.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import numpy as np

from app.insights.basket_index import UNKNOWN_CATEGORY, BasketIndex


def compute_affinity_network(
    index: BasketIndex,
    alpha: float = 0.05,
    min_support: int = 2,
    max_orphans: int = 15,
) -> dict[str, Any]:
    edges = [
        {
            "source": a,
            "target": b,
            "support": s.support,
            "lift": round(s.lift, 3),
            "p_value": float(f"{s.p_value:.3g}"),
            "q_value": float(f"{s.q_value:.3g}"),
            "cross_category": index.cat(a) != index.cat(b),
        }
        for (a, b), s in index.significant_pairs(alpha, min_support)
    ]

    degree: dict[str, int] = defaultdict(int)
    strength: dict[str, int] = defaultdict(int)
    partner_cats: dict[str, Counter] = defaultdict(Counter)
    for e in edges:
        a, b = e["source"], e["target"]
        for x, y in ((a, b), (b, a)):
            degree[x] += 1
            strength[x] += e["support"]
            partner_cats[x][index.cat(y)] += 1

    connected_degrees = list(degree.values())
    hub_threshold = max(3, int(np.ceil(np.percentile(connected_degrees, 90)))) if connected_degrees else 3

    nodes = []
    for pid in index.product_support:
        k = degree.get(pid, 0)
        own = index.cat(pid)
        cats = partner_cats.get(pid, Counter())
        participation = 1 - sum((kc / k) ** 2 for kc in cats.values()) if k else 0.0
        other_cats = set(cats) - {own, UNKNOWN_CATEGORY}
        if k >= hub_threshold:
            role = "hub"
        elif k >= 2 and participation >= 0.5 and len(other_cats) >= 2:
            role = "bridge"
        elif k == 0:
            role = "orphan"
        else:
            role = "standard"
        nodes.append({
            "product_id": pid,
            "name": index.label(pid),
            "category": own,
            "price": round(index.price.get(pid, 0.0), 2),
            "revenue": round(index.product_revenue.get(pid, 0.0), 2),
            "baskets": index.product_support[pid],
            "degree": k,
            "strength": strength.get(pid, 0),
            "participation": round(participation, 3),
            "role": role,
            "connected_categories": sorted(cats),
        })

    role_counts = Counter(n["role"] for n in nodes)
    orphans = sorted((n for n in nodes if n["role"] == "orphan"), key=lambda n: n["revenue"], reverse=True)
    drawn_ids = {n["product_id"] for n in nodes if n["degree"] > 0} | {n["product_id"] for n in orphans[:max_orphans]}
    drawn_nodes = sorted((n for n in nodes if n["product_id"] in drawn_ids), key=lambda n: n["degree"], reverse=True)
    n_nodes = len(nodes)

    return {
        "nodes": drawn_nodes,
        "edges": edges,
        "orphans": orphans,
        "summary": {
            "total_products": n_nodes,
            "pairs_tested": len(index.pair_stats),
            "total_edges": len(edges),
            "cross_category_edges": sum(e["cross_category"] for e in edges),
            "drawn_nodes": len(drawn_nodes),
            "hub_count": role_counts["hub"],
            "bridge_count": role_counts["bridge"],
            "standard_count": role_counts["standard"],
            "orphan_count": role_counts["orphan"],
            "hub_degree_threshold": hub_threshold,
            "density": round(2 * len(edges) / (n_nodes * (n_nodes - 1)), 4) if n_nodes > 1 else 0.0,
        },
        "params": {"alpha": alpha, "min_support": min_support},
    }
