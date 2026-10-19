"""HTTP routes for the Insights layer (mounted under /insights)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.insights import service
from app.insights.affinity_network import compute_affinity_network
from app.insights.category_heatmap import compute_category_heatmap
from app.insights.promotion_optimizer import PromotionAssumptions, compute_promotion_optimizer
from app.insights.revenue_opportunity import compute_revenue_opportunity
from app.insights.seasonal_trends import compute_seasonal_trends
from app.pipeline import store

router = APIRouter(prefix="/insights", tags=["insights"])
_DEFAULTS = PromotionAssumptions()


def _index(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(404, f"Unknown run_id '{run_id}'")
    if run["status"] != "completed":
        raise HTTPException(409, f"Run '{run_id}' must be completed for insights (status={run['status']})")
    try:
        return service.get_index(run_id)
    except service.InsightDataMissing as e:
        raise HTTPException(404, str(e))


@router.get("/all/{run_id}")
def all_insights(run_id: str):
    _index(run_id)
    return {"run_id": run_id, **service.compute_all(run_id)}


@router.get("/category-heatmap/{run_id}")
def category_heatmap(run_id: str):
    return {"run_id": run_id, **compute_category_heatmap(_index(run_id))}


@router.get("/revenue-opportunity/{run_id}")
def revenue_opportunity(run_id: str, top_n: int = Query(20, ge=1, le=200)):
    return {"run_id": run_id, **compute_revenue_opportunity(_index(run_id), top_n=top_n)}


@router.get("/affinity-network/{run_id}")
def affinity_network(run_id: str, alpha: float = Query(0.05, gt=0, lt=1), min_support: int = Query(2, ge=1)):
    return {"run_id": run_id, **compute_affinity_network(_index(run_id), alpha=alpha, min_support=min_support)}


@router.get("/action-cards/{run_id}")
def action_cards(run_id: str):
    _index(run_id)
    return {"run_id": run_id, **service.compute_all(run_id)["action_cards"]}


@router.get("/promotion-optimizer/{run_id}")
def promotion_optimizer(
    run_id: str,
    nudge_window: float = Query(_DEFAULTS.nudge_window, gt=0, lt=1),
    nudge_conversion: float = Query(_DEFAULTS.nudge_conversion, ge=0, le=1),
    shipping_cost: float = Query(_DEFAULTS.shipping_cost, ge=0),
    gross_margin: float = Query(_DEFAULTS.gross_margin, gt=0, le=1),
    discount_elasticity: float = Query(_DEFAULTS.discount_elasticity, ge=0),
):
    a = PromotionAssumptions(
        nudge_window=nudge_window,
        nudge_conversion=nudge_conversion,
        shipping_cost=shipping_cost,
        gross_margin=gross_margin,
        discount_elasticity=discount_elasticity,
    )
    return {"run_id": run_id, **compute_promotion_optimizer(_index(run_id), a)}


@router.get("/seasonal-trends/{run_id}")
def seasonal_trends(run_id: str, alpha: float = Query(0.05, gt=0, lt=1)):
    return {"run_id": run_id, **compute_seasonal_trends(_index(run_id), alpha=alpha)}
