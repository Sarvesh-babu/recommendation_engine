"""Attaches a human-readable "why was this recommended" reason -- and a
display name -- to each recommended product_id/customer_id, on top of
whichever model produced the ranked list.

This is a post-hoc explanation layer, not a property the models compute
internally: for content-based and frequently-bought-together the reason
is the literal signal the ranking used; for the matrix-factorization
variants (ALS/BPR/neural hybrid) it's the strongest matching signal found
in the customer's own history, which is an approximation of the latent
factors actually driving the score.
"""
import pandas as pd


def build_name_map(df: pd.DataFrame, id_col: str) -> dict[str, str]:
    """id -> display name, falling back to the id itself when no 'name'
    column was supplied (e.g. older uploads predating this feature)."""
    if "name" not in df.columns:
        return {v: v for v in df[id_col].unique()}
    return dict(zip(df[id_col], df["name"].fillna(df[id_col])))


def _customer_top_attributes(txn: pd.DataFrame, products_df: pd.DataFrame, customer_id: str) -> tuple[str | None, str | None]:
    history = txn.loc[txn["customer_id"] == customer_id, "product_id"]
    if history.empty:
        return None, None
    merged = products_df.set_index("product_id").reindex(history)
    top_category = merged["category"].mode().iat[0] if "category" in merged.columns and not merged["category"].dropna().empty else None
    top_brand = merged["brand"].mode().iat[0] if "brand" in merged.columns and not merged["brand"].dropna().empty else None
    return top_category, top_brand


def enrich_personalized(
    personalized: dict[str, list[str]],
    txn: pd.DataFrame,
    products_df: pd.DataFrame,
    product_names: dict[str, str],
    variant: str,
) -> dict[str, list[dict]]:
    prod_attrs = products_df.set_index("product_id")
    enriched: dict[str, list[dict]] = {}
    for customer_id, product_ids in personalized.items():
        top_category, top_brand = _customer_top_attributes(txn, products_df, customer_id)
        items = []
        for pid in product_ids:
            reason = _personalized_reason(pid, prod_attrs, top_category, top_brand, variant)
            items.append({"product_id": pid, "name": product_names.get(pid, pid), "reason": reason})
        enriched[customer_id] = items
    return enriched


def _personalized_reason(
    product_id: str,
    prod_attrs: pd.DataFrame,
    top_category: str | None,
    top_brand: str | None,
    variant: str,
) -> str:
    row = prod_attrs.loc[product_id] if product_id in prod_attrs.index else None
    category = row.get("category") if row is not None else None
    brand = row.get("brand") if row is not None else None

    if variant == "content_based":
        if category and category == top_category and brand and brand == top_brand:
            return f"Matches your most-bought brand and category ({brand}, {category})"
        if category and category == top_category:
            return f"Matches your most-purchased category ({category})"
        if brand and brand == top_brand:
            return f"From a brand you buy often ({brand})"
        return "Closest match to your overall purchase profile"

    if category and category == top_category and brand and brand == top_brand:
        return f"Matches your most-bought brand and category ({brand}, {category})"
    if category and category == top_category:
        return f"Matches your most-purchased category ({category})"
    if brand and brand == top_brand:
        return f"From a brand you buy often ({brand})"
    return "Customers with similar purchase patterns also bought this"


def enrich_fbt(
    fbt: dict[str, list[str]],
    txn: pd.DataFrame,
    product_names: dict[str, str],
) -> dict[str, list[dict]]:
    basket_groups = txn.groupby("transaction_id")["product_id"].apply(set)
    enriched: dict[str, list[dict]] = {}
    for anchor_id, product_ids in fbt.items():
        anchor_name = product_names.get(anchor_id, anchor_id)
        shared_baskets = [b for b in basket_groups if anchor_id in b]
        items = []
        for pid in product_ids:
            n_shared = sum(1 for b in shared_baskets if pid in b)
            if n_shared > 0:
                reason = f"Bought together with {anchor_name} in {n_shared} past order(s)"
            else:
                reason = f"Commonly purchased alongside {anchor_name}"
            items.append({"product_id": pid, "name": product_names.get(pid, pid), "reason": reason})
        enriched[anchor_id] = items
    return enriched


def enrich_cart(ranked_candidates: list[dict], product_names: dict[str, str]) -> list[dict]:
    """Same {product_id, name, reason} shape as enrich_fbt, but the reason
    credits every cart item that contributed to a candidate's ranking
    (ranked_candidates already carries those per-candidate contribution
    counts from cart_cooccurrence_recommendations, so no basket re-scan is
    needed here)."""
    enriched = []
    for entry in ranked_candidates:
        pid = entry["product_id"]
        contributions = sorted(entry["contributing_cart_items"].items(), key=lambda kv: -kv[1])
        parts = [f"{product_names.get(cid, cid)} ({n} order(s))" for cid, n in contributions]
        reason = "Bought together with " + ", ".join(parts)
        enriched.append({"product_id": pid, "name": product_names.get(pid, pid), "reason": reason})
    return enriched


def enrich_popularity(
    popularity: dict[str, list[str]],
    product_names: dict[str, str],
    variant: str,
) -> dict[str, list[dict]]:
    enriched: dict[str, list[dict]] = {}
    for segment_key, product_ids in popularity.items():
        if variant == "trending_velocity":
            reason = "Trending this week" if segment_key == "overall" else f"Trending this week among {segment_key.split(':', 1)[-1]} customers"
        else:
            reason = "Best seller overall" if segment_key == "overall" else f"Best seller among {segment_key.split(':', 1)[-1]} customers"
        enriched[segment_key] = [
            {"product_id": pid, "name": product_names.get(pid, pid), "reason": reason} for pid in product_ids
        ]
    return enriched
