"""Insights layer — portfolio-level merchandising intelligence.

Sits on top of the run's cleaned transactions/products, independent of the
recommendation pipeline. Six modules share one BasketIndex:

    category_heatmap      Category cross-sell heatmap (confidence + lift)
    revenue_opportunity   Revenue opportunity sizing (gap × attach × price)
    affinity_network      Product affinity network (hubs, bridges, orphans)
    action_cards          Auto-generated merchandising action cards
    promotion_optimizer   Free-shipping threshold & bundle discount simulator
    seasonal_trends       Volume-normalised seasonal pairs + category momentum

All computations are deterministic (no LLM calls).
"""
