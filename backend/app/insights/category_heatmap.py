"""1. Category Cross-Sell Heatmap.

For categories X (row) and Y (column), over baskets that contain at least one
categorised product:

    n(X)       baskets containing any product of category X
    n(X,Y)     baskets containing products of both X and Y
    conf(X→Y)  P(Y | X) = n(X,Y) / n(X)                 — asymmetric
    lift(X,Y)  n(X,Y)·N / (n(X)·n(Y))                   — symmetric, 1.0 = independent

The diagonal is undefined for both measures (P(X|X) is always 100%), so it is
returned as null and the row's own basket share is reported separately.
Cells with n(X,Y) below `min_cell_support` are flagged as low-support.

Each category pair is tested against independence with a two-sided
hypergeometric test, p = min(1, 2·min(P(X ≥ n), P(X ≤ n))), BH-adjusted
across all pairs. `association` is positive / negative when q < alpha,
otherwise independent. Only significant pairs are reported as strongest /
weakest.
"""
from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Any

import numpy as np

from app.insights.basket_index import (
    UNKNOWN_CATEGORY,
    BasketIndex,
    association_p_values,
    bh_adjust,
    confidence,
    lift,
)


def compute_category_heatmap(index: BasketIndex, min_cell_support: int = 5, alpha: float = 0.05) -> dict[str, Any]:
    if not index.has_categories:
        return {"error": "No category column found in products data"}

    basket_cats = []
    for items in index.baskets.values():
        cats = {index.cat(p) for p in items} - {UNKNOWN_CATEGORY}
        if cats:
            basket_cats.append(cats)

    n_total = len(basket_cats)
    support: Counter = Counter()
    co: Counter = Counter()
    for cats in basket_cats:
        support.update(cats)
        co.update(combinations(sorted(cats), 2))

    categories = sorted(support)
    if len(categories) < 2:
        return {"error": "Fewer than 2 categories found — cannot build heatmap"}

    pairs = list(combinations(categories, 2))
    p_over, p_under = association_p_values(
        [co[p] for p in pairs], [support[x] for x, _ in pairs], [support[y] for _, y in pairs], n_total
    )
    q = bh_adjust(np.minimum(1.0, 2 * np.minimum(p_over, p_under)))
    q_of = {p: float(q[i]) for i, p in enumerate(pairs)}

    cells = []
    for row in categories:
        for col in categories:
            if row == col:
                cells.append({"row": row, "col": col, "count": support[row], "confidence_pct": None,
                              "lift": None, "q_value": None, "association": None, "low_support": False})
                continue
            key = (row, col) if row < col else (col, row)
            n_xy = co[key]
            cell_lift = lift(n_xy, support[row], support[col], n_total)
            significant = q_of[key] < alpha
            cells.append({
                "row": row,
                "col": col,
                "count": n_xy,
                "confidence_pct": round(confidence(n_xy, support[row]) * 100, 1),
                "lift": round(cell_lift, 3),
                "q_value": float(f"{q_of[key]:.3g}"),
                "association": ("positive" if cell_lift > 1 else "negative") if significant else "independent",
                "low_support": n_xy < min_cell_support,
            })

    upper = [c for c in cells if c["row"] < c["col"]]
    strongest = sorted((c for c in upper if c["association"] == "positive"), key=lambda c: c["lift"], reverse=True)[:5]
    weakest = sorted((c for c in upper if c["association"] == "negative"), key=lambda c: c["lift"])[:5]

    return {
        "categories": categories,
        "cells": cells,
        "support_counts": {c: support[c] for c in categories},
        "basket_share_pct": {c: round(support[c] / n_total * 100, 1) for c in categories},
        "total_baskets": n_total,
        "multi_category_baskets": sum(1 for c in basket_cats if len(c) > 1),
        "min_cell_support": min_cell_support,
        "alpha": alpha,
        "strongest_pairs": [_pair(c) for c in strongest],
        "weakest_pairs": [_pair(c) for c in weakest],
    }


def _pair(cell: dict) -> dict:
    return {"category_a": cell["row"], "category_b": cell["col"], "count": cell["count"],
            "lift": cell["lift"], "q_value": cell["q_value"]}
