"""Adaptive feature engineering: behavioral/temporal features are always
computed; optional feature groups activate only when their source file
was uploaded. Gates fail soft -- a missing optional file just skips that
feature group rather than erroring the run.
"""
import numpy as np
import pandas as pd


def filter_features_for_modeling(
    df: pd.DataFrame,
    id_cols: list[str] = None,
    max_correlation_threshold: float = 0.95
) -> list[str]:
    """
    Filters features to ensure no skewed, zero-variance, or redundant (highly correlated) features
    are passed into downstream modeling or side-feature matrices.

    Rules applied:
    1. Remove ID/Key columns.
    2. Remove zero-variance / constant / low-variance columns (std == 0 or nunique <= 1).
    3. Remove high-null columns (> 90% nulls).
    4. Handle Paired Raw vs Transformed Features:
       If both 'X' and 'X_log' (or 'X_squared') exist:
       - If raw 'X' has high skewness (|skew| > 0.75), drop raw 'X' and keep 'X_log'.
       - If raw 'X' has low skewness (|skew| <= 0.75), drop 'X_log' and keep raw 'X'.
    5. Multicollinearity & Redundancy Filtering:
       If pair (col_A, col_B) has |Pearson correlation| > max_correlation_threshold (0.85):
       - Keep the feature with lower absolute skewness and higher variance/completeness.
       - Drop the redundant feature.
    """
    if df is None or df.empty:
        return []

    id_cols_set = set(id_cols or [])

    # Candidate numeric selection
    candidates = []
    for c in df.select_dtypes(include=[np.number]).columns:
        c_lower = c.lower()
        if c in id_cols_set:
            continue
        if any(c_lower.endswith(s) for s in ["_id", "_uuid", "_pk", "_fk", "_key"]):
            continue
        if c_lower in ["id", "timestamp", "index"]:
            continue

        series = df[c].dropna()
        if len(series) < 2:
            continue
        if series.nunique() <= 1 or df[c].std() == 0:
            continue
        if df[c].isna().mean() > 0.90:
            continue

        candidates.append(c)

    if not candidates:
        return []

    # Paired Raw vs Transformed selection
    to_drop = set()
    for col in candidates:
        for suf in ["_log", "_squared", "_binned", "_sqrt"]:
            if col.endswith(suf):
                parent = col[:-len(suf)]
                if parent in candidates:
                    raw_skew = abs(df[parent].dropna().skew()) if len(df[parent].dropna()) > 5 else 0.0
                    if raw_skew > 0.75:
                        to_drop.add(parent)
                    else:
                        to_drop.add(col)

    valid_candidates = [c for c in candidates if c not in to_drop]

    if len(valid_candidates) <= 1:
        return valid_candidates

    # Correlation / Multicollinearity filtering
    corr = df[valid_candidates].corr().abs()
    cols_to_keep = list(valid_candidates)

    for i in range(len(valid_candidates)):
        c1 = valid_candidates[i]
        if c1 not in cols_to_keep:
            continue
        for j in range(i + 1, len(valid_candidates)):
            c2 = valid_candidates[j]
            if c2 not in cols_to_keep:
                continue

            r_val = corr.loc[c1, c2]
            if not np.isnan(r_val) and r_val > max_correlation_threshold:
                # Compare skewness; drop the one with higher skewness
                sk1 = abs(df[c1].dropna().skew()) if len(df[c1].dropna()) > 5 else 0.0
                sk2 = abs(df[c2].dropna().skew()) if len(df[c2].dropna()) > 5 else 0.0

                dropped = c1 if sk1 > sk2 else c2
                if dropped in cols_to_keep:
                    cols_to_keep.remove(dropped)

    return cols_to_keep


def build_features(dataframes: dict[str, pd.DataFrame], layer1_dfs: dict[str, pd.DataFrame] = None) -> tuple[dict, dict]:
    """Extracts features prioritizing Layer 1 engineered dataframes, falling back
    adaptively to raw dataframe calculations if Layer 1 data is absent.
    Returns (features_dict, provenance_metadata).
    """
    dfs = layer1_dfs if layer1_dfs is not None else dataframes

    cust_df = dfs.get("customers")
    prod_df = dfs.get("products")
    has_layer1_features = False
    if cust_df is not None and not cust_df.empty:
        has_layer1_features = has_layer1_features or any(
            c in cust_df.columns for c in ["user_monetary_total_log", "user_frequency_count", "user_recency_days", "user_avg_unit_price"]
        )
    if prod_df is not None and not prod_df.empty:
        has_layer1_features = has_layer1_features or any(
            c in prod_df.columns for c in ["item_total_revenue_log", "item_units_sold", "net_demand"]
        )

    is_layer1_active = (layer1_dfs is not None) or has_layer1_features

    provenance = {
        "source": "LAYER1_ENGINEERED_FEATURE_STORE" if is_layer1_active else "LOCAL_COMPUTED_FALLBACK",
        "features_loaded": [],
        "fallbacks_applied": []
    }

    txn = dfs["transactions"].copy()
    txn["timestamp"] = pd.to_datetime(txn["timestamp"], errors="coerce")

    features: dict = {}
    features["behavioral"] = _behavioral_features(txn, dfs.get("customers"))
    features["temporal"] = _temporal_features(txn, dfs.get("customers"))

    provenance["features_loaded"].extend(["behavioral_rfm", "temporal_recency"])

    if "sessions" in dfs:
        features["session_affinity"] = _session_affinity(dfs["sessions"])
        provenance["features_loaded"].append("session_affinity")
    if "returns" in dfs:
        features["returns_adjusted_demand"] = _returns_adjusted_demand(txn, dfs["returns"])
        provenance["features_loaded"].append("returns_adjusted_demand")
    if "search_logs" in dfs:
        features["search_intent"] = _search_intent(dfs["search_logs"])
        provenance["features_loaded"].append("search_intent")
    if "promotions" in dfs:
        features["promotion_sensitivity"] = _promotion_sensitivity(txn, dfs["promotions"])
        provenance["features_loaded"].append("promotion_sensitivity")

    return features, provenance


def _behavioral_features(txn: pd.DataFrame, customers_df: pd.DataFrame = None) -> pd.DataFrame:
    # If Layer 1 already calculated RFM columns, reuse them directly
    if customers_df is not None and not customers_df.empty:
        cols = [c for c in ["user_monetary_total_log", "user_frequency_count", "user_avg_unit_price", "total_spend", "n_orders"] if c in customers_df.columns]
        if "customer_id" in customers_df.columns and len(cols) > 0:
            return customers_df[["customer_id"] + cols].copy()

    # Fallback derivation
    agg = txn.groupby("customer_id").agg(
        total_spend=("price", lambda s: float((s * txn.loc[s.index, "quantity"]).sum())),
        n_orders=("transaction_id", "nunique"),
        n_distinct_products=("product_id", "nunique"),
    ).reset_index()
    agg["user_monetary_total_log"] = np.log1p(np.maximum(0, agg["total_spend"]))
    agg["user_frequency_count"] = agg["n_orders"]
    return agg


def _temporal_features(txn: pd.DataFrame, customers_df: pd.DataFrame = None) -> pd.DataFrame:
    # If Layer 1 already calculated recency_days, reuse it directly
    if customers_df is not None and not customers_df.empty and "user_recency_days" in customers_df.columns:
        return customers_df[["customer_id", "user_recency_days"]].rename(columns={"user_recency_days": "recency_days"})

    valid = txn.dropna(subset=["timestamp"])
    if valid.empty:
        return pd.DataFrame(columns=["customer_id", "recency_days", "last_purchase"])
    now = valid["timestamp"].max()
    agg = valid.groupby("customer_id")["timestamp"].max().reset_index()
    agg["recency_days"] = (now - agg["timestamp"]).dt.days
    agg = agg.rename(columns={"timestamp": "last_purchase"})
    return agg


def _session_affinity(sessions: pd.DataFrame) -> pd.DataFrame:
    return sessions.groupby(["customer_id", "product_id"]).size().reset_index(name="session_views")


def _returns_adjusted_demand(txn: pd.DataFrame, returns: pd.DataFrame) -> pd.DataFrame:
    sold = txn.groupby("product_id")["quantity"].sum().rename("units_sold")
    returned = returns.groupby("product_id").size().rename("units_returned")
    out = pd.concat([sold, returned], axis=1).fillna(0).reset_index()
    out["net_demand"] = out["units_sold"] - out["units_returned"]
    return out


def _search_intent(search_logs: pd.DataFrame) -> pd.DataFrame:
    return search_logs.groupby("customer_id")["query"].count().reset_index(name="n_searches")


def _promotion_sensitivity(txn: pd.DataFrame, promotions: pd.DataFrame) -> pd.DataFrame:
    promoted_products = set(promotions["product_id"])
    txn = txn.copy()
    txn["was_promoted"] = txn["product_id"].isin(promoted_products)
    return txn.groupby("customer_id")["was_promoted"].mean().reset_index(name="promo_purchase_rate")

