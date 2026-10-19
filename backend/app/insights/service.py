"""Orchestrates the Insights layer for a run.

The BasketIndex for a run is cached and keyed on the source files' mtimes, so
the six modules — and repeated optimizer calls with different assumptions —
share one pass over the transactions.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from app.config import RUNS_DIR
from app.insights.action_cards import generate_action_cards
from app.insights.affinity_network import compute_affinity_network
from app.insights.basket_index import BasketIndex, build_basket_index
from app.insights.category_heatmap import compute_category_heatmap
from app.insights.promotion_optimizer import PromotionAssumptions, compute_promotion_optimizer
from app.insights.revenue_opportunity import compute_revenue_opportunity
from app.insights.seasonal_trends import compute_seasonal_trends


class InsightDataMissing(Exception):
    pass


def run_files(run_id: str) -> tuple[Path, Path]:
    run_dir = RUNS_DIR / run_id
    txn, products = run_dir / "transactions.csv", run_dir / "products.csv"
    if not txn.exists() or not products.exists():
        raise InsightDataMissing(f"Missing transactions or products data for run '{run_id}'")
    return txn, products


def get_index(run_id: str) -> BasketIndex:
    txn, products = run_files(run_id)
    return _cached_index(str(txn), txn.stat().st_mtime, str(products), products.stat().st_mtime)


def get_index_or_build(run_id: str, txn: pd.DataFrame) -> BasketIndex:
    """Cached index when the run has products.csv; otherwise built from transactions alone."""
    try:
        return get_index(run_id)
    except InsightDataMissing:
        return build_basket_index(txn, None)


@lru_cache(maxsize=8)
def _cached_index(txn_path: str, _txn_mtime: float, products_path: str, _products_mtime: float) -> BasketIndex:
    return build_basket_index(pd.read_csv(txn_path), pd.read_csv(products_path))


def _safe(fn: Callable[[], dict]) -> dict:
    try:
        return fn()
    except Exception as e:  # one failing module must not take down the dashboard
        return {"error": f"{type(e).__name__}: {e}"}


def compute_all(run_id: str, assumptions: PromotionAssumptions | None = None) -> dict[str, Any]:
    index = get_index(run_id)
    modules = {
        "category_heatmap": _safe(lambda: compute_category_heatmap(index)),
        "revenue_opportunity": _safe(lambda: compute_revenue_opportunity(index)),
        "affinity_network": _safe(lambda: compute_affinity_network(index)),
        "promotion_optimizer": _safe(lambda: compute_promotion_optimizer(index, assumptions)),
        "seasonal_trends": _safe(lambda: compute_seasonal_trends(index)),
    }
    modules["action_cards"] = _safe(lambda: generate_action_cards(index, modules))
    return {"overview": overview(index), **modules}


def overview(index: BasketIndex) -> dict[str, Any]:
    sizes = [len(b) for b in index.baskets.values()]
    return {
        "baskets": index.n_baskets,
        "customers": index.n_customers,
        "products": len(index.product_support),
        "revenue": round(index.total_revenue, 2),
        "avg_items_per_basket": round(sum(sizes) / len(sizes), 2) if sizes else 0.0,
        "multi_item_basket_pct": round(sum(s > 1 for s in sizes) / len(sizes) * 100, 1) if sizes else 0.0,
        "distinct_pairs": len(index.pair_support),
    }
