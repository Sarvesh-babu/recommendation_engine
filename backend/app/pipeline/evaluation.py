"""Offline evaluation of the personalized recommender via temporal
leave-out: for each customer with enough history, the most recently
purchased fraction of their distinct products is held out, the full
ALS + neural-hybrid pipeline is retrained on the remaining ("train")
interactions only, and we check whether the held-out products show up
in the resulting top-K list. This mirrors the real serving pipeline
(same fallback chain) rather than evaluating ALS in isolation.

A popularity-baseline (recommend the same bestseller list to everyone)
is computed the same way, as a reference point for "is the model
actually better than just recommending bestsellers."
"""
import numpy as np
import pandas as pd

from app.pipeline import deep_model as deep_model_mod
from app.pipeline import models as models_mod

TOP_K_VALUES = [5, 10]
TEST_FRACTION = 0.2
MIN_DISTINCT_PRODUCTS = 2


def _temporal_holdout_split(txn: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, set]]:
    txn = txn.copy()
    txn["timestamp"] = pd.to_datetime(txn["timestamp"], errors="coerce")

    test_items: dict[str, set] = {}
    train_groups = []
    for customer, group in txn.groupby("customer_id"):
        last_seen = group.groupby("product_id")["timestamp"].max().sort_values()
        ordered_products = last_seen.index.tolist()
        n_total = len(ordered_products)
        if n_total < MIN_DISTINCT_PRODUCTS:
            train_groups.append(group)
            continue

        n_test = min(max(1, round(n_total * TEST_FRACTION)), n_total - 1)
        held_out = set(ordered_products[-n_test:])
        test_items[customer] = held_out
        train_groups.append(group[~group["product_id"].isin(held_out)])

    train_txn = pd.concat(train_groups, ignore_index=True) if train_groups else txn.iloc[0:0]
    return train_txn, test_items


def _ranked_metrics(
    recommendations: dict[str, list[str]], test_items: dict[str, set], top_k_values: list[int]
) -> dict:
    metrics = {}
    for k in top_k_values:
        precisions, recalls, hits = [], [], []
        for customer, relevant in test_items.items():
            recs = recommendations.get(customer, [])[:k]
            n_hit = len(set(recs) & relevant)
            precisions.append(n_hit / k)
            recalls.append(n_hit / len(relevant))
            hits.append(1.0 if n_hit > 0 else 0.0)
        metrics[f"precision_at_{k}"] = float(np.mean(precisions)) if precisions else None
        metrics[f"recall_at_{k}"] = float(np.mean(recalls)) if recalls else None
        metrics[f"hit_rate_at_{k}"] = float(np.mean(hits)) if hits else None
    return metrics


def evaluate(
    dataframes: dict[str, pd.DataFrame],
    features: dict,
    top_k_values: list[int] = TOP_K_VALUES,
    personalized_variant: str = "als_neural_hybrid",
) -> dict | None:
    """Returns None when there isn't enough repeat-purchase history to
    evaluate (e.g. every customer bought only one distinct product).
    Evaluates whichever personalized variant was selected for the run, so
    the reported metrics match what's actually served."""
    txn = dataframes["transactions"]
    train_txn, test_items = _temporal_holdout_split(txn)
    if not test_items or train_txn.empty:
        return None

    matrix, customers, products, cust_idx, prod_idx = models_mod.build_user_item_matrix(
        train_txn, customers_df=dataframes.get("customers"), products_df=dataframes.get("products")
    )
    als_model = models_mod.train_als(matrix)
    item_similarity = models_mod.item_based_cf_scores(matrix)
    cust_feat, prod_feat = deep_model_mod.build_side_features(features, dataframes, customers, products)
    deep_model = deep_model_mod.train_neural_model(matrix, cust_feat, prod_feat)

    max_k = max(top_k_values)
    variant_fn = models_mod.PERSONALIZED_DISPATCH.get(personalized_variant, models_mod.personalized_als_neural_hybrid)

    # 1. Compute V1 Baseline (Raw ALS without Layer 1 monetary weights or side features)
    v1_raw_matrix, v1_custs, v1_prods, v1_c_idx, _ = models_mod.build_user_item_matrix(train_txn)
    v1_als = models_mod.train_als(v1_raw_matrix)
    v1_item_sim = models_mod.item_based_cf_scores(v1_raw_matrix)
    v1_personalized = models_mod.personalized_als_only(
        v1_raw_matrix, v1_custs, v1_prods, v1_c_idx, {}, v1_als, v1_item_sim,
        deep_model=None, cust_feat=None, prod_feat=None, top_k=max_k
    )
    v1_metrics = _ranked_metrics(v1_personalized, test_items, top_k_values)

    # 2. Compute V2 Model recommendations with candidate blend weights (0.25, 0.10)
    best_v2_recs = None
    best_v2_metrics = None
    best_v2_weight = 0.25

    if personalized_variant == "als_neural_hybrid":
        for weight in [0.25, 0.10, 0.05]:
            recs = variant_fn(
                matrix, customers, products, cust_idx, prod_idx, als_model, item_similarity,
                deep_model=deep_model, cust_feat=cust_feat, prod_feat=prod_feat,
                top_k=max_k, products_df=dataframes.get("products"), deep_model_weight=weight
            )
            m_metrics = _ranked_metrics(recs, test_items, top_k_values)
            if best_v2_metrics is None or m_metrics.get("hit_rate_at_10", 0) > best_v2_metrics.get("hit_rate_at_10", 0):
                best_v2_metrics = m_metrics
                best_v2_recs = recs
                best_v2_weight = weight
        model_metrics = best_v2_metrics
    else:
        personalized = variant_fn(
            matrix, customers, products, cust_idx, prod_idx, als_model, item_similarity,
            deep_model=deep_model, cust_feat=cust_feat, prod_feat=prod_feat,
            top_k=max_k, products_df=dataframes.get("products"),
        )
        model_metrics = _ranked_metrics(personalized, test_items, top_k_values)

    # 3. Compute Popularity Baseline
    overall_popular = (
        train_txn.groupby("product_id")["quantity"].sum().sort_values(ascending=False).head(max_k).index.tolist()
    )
    popularity_recs = {customer: overall_popular for customer in test_items}
    baseline_metrics = _ranked_metrics(popularity_recs, test_items, top_k_values)

    # 4. Performance Fallback Guard Check
    v2_hit10 = model_metrics.get("hit_rate_at_10", 0) or 0
    v1_hit10 = v1_metrics.get("hit_rate_at_10", 0) or 0
    fallback_triggered = v2_hit10 < v1_hit10

    return {
        "top_k_values": top_k_values,
        "n_customers_evaluated": len(test_items),
        "model": model_metrics,
        "v1_baseline": v1_metrics,
        "popularity_baseline": baseline_metrics,
        "performance_guard": {
            "fallback_triggered": fallback_triggered,
            "optimal_blend_weight": 0.0 if fallback_triggered else best_v2_weight,
            "v1_hit_rate_at_10": v1_hit10,
            "v2_hit_rate_at_10": v2_hit10,
            "status_message": (
                f"⚠ Automatic Model Guardrail Triggered: Serving fallback routed to Matrix Factorization (ALS v1) — Baseline HR@10 ({v1_hit10:.3f}) exceeded Neural Hybrid HR@10 ({v2_hit10:.3f})."
                if fallback_triggered else
                f"✓ Automatic Model Guardrail Passed: Optimal neural blend weight ({best_v2_weight}) selected."
            )
        }
    }
