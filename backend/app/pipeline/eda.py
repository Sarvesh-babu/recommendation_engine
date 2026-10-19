"""
Dynamic EDA Summary Engine for Recommendation Accelerator.

Scans all active tables (transactions, customers, products, sessions, returns, search_logs, promotions)
to compute distributions, correlation matrices, column stats, and category breakdowns.
Includes Step 1 deterministic feature filtering & Layer 1 dynamic feature lineage tracking.
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Set


def run_eda(dataframes: Dict[str, pd.DataFrame], raw_schemas: Dict[str, List[str]] = None) -> Dict[str, Any]:
    txn = dataframes.get("transactions", pd.DataFrame())
    customers = dataframes.get("customers", pd.DataFrame())
    products = dataframes.get("products", pd.DataFrame())

    # Convert raw_schemas list representation to sets for O(1) dynamic lookup
    raw_schema_sets = {}
    if raw_schemas:
        for t_name, cols in raw_schemas.items():
            raw_schema_sets[t_name] = set(cols)

    # Build aligned transaction-level feature matrix incorporating raw + engineered features from ALL active tables
    aligned_df = _build_aligned_numeric_df(dataframes)

    # Step 1: Select top filtered features for visual charts (Distributions & Correlations)
    selected_features = _filter_features_for_analysis(aligned_df, raw_schema_sets=raw_schema_sets, max_cols=12)
    chart_df = aligned_df[selected_features] if not aligned_df.empty and selected_features else pd.DataFrame()

    summary = {
        "n_transactions": int(len(txn)),
        "n_customers": int(customers["customer_id"].nunique()) if "customer_id" in customers else 0,
        "n_products": int(products["product_id"].nunique()) if "product_id" in products else 0,
        "n_customers_with_transactions": int(txn["customer_id"].nunique()) if "customer_id" in txn else 0,
        "n_products_with_transactions": int(txn["product_id"].nunique()) if "product_id" in txn else 0,
        "sparsity": _sparsity(txn, customers, products),
        "top_products": _top_products(txn),
        "transactions_over_time": _transactions_over_time(txn),
    }

    # Category & Segment Pie Chart Breakdowns
    category_col = _detect_column(products, ["category", "dept", "department", "type"])
    if category_col:
        summary["category_breakdown"] = category_breakdown(txn, products, category_col)

    segment_col = _detect_column(customers, ["segment", "tier", "age_group", "gender"])
    if segment_col:
        summary["segment_breakdown"] = segment_breakdown(txn, customers, segment_col)

    # Dynamic Column Stats, Distributions & Correlations with Layer 1 Lineage & Filtered Features
    summary["column_stats"] = _compute_column_stats(dataframes, raw_schema_sets=raw_schema_sets, selected_chart_features=set(selected_features))
    summary["numeric_distributions"] = _compute_numeric_distributions(chart_df, max_cols=12)
    summary["correlation_matrix"] = _compute_correlation_matrix(chart_df, max_cols=12)
    summary["categorical_breakdowns"] = _compute_categorical_breakdowns(txn, products)
    summary["selected_chart_features"] = selected_features

    # Enhanced: Overview stats for dashboard cards
    summary["overview_stats"] = _compute_overview_stats(dataframes, aligned_df, summary)

    # Enhanced: Auto-generated textual insights
    summary["insights"] = _generate_insights(summary, aligned_df)

    return _sanitize_dict_for_json(summary)


def _detect_key_column(col_name: str) -> bool:
    """Returns True if col_name is an ID, UUID, or key column."""
    name_lower = col_name.lower()
    if name_lower.endswith(("_id", "_uuid", "_pk", "_fk", "_key")):
        return True
    if name_lower in ("id", "uuid", "index", "customer", "product", "transaction", "session", "promotion"):
        return True
    return False


RAW_COLUMNS = {
    "transaction_id", "customer_id", "product_id", "session_id", "promotion_id",
    "quantity", "price", "timestamp", "date", "amount",
    "age", "gender", "segment", "signup_date", "country", "city",
    "category", "brand", "department", "unit_cost",
    "query", "discount_pct", "start_date", "end_date", "return_reason", "return_date"
}


def _detect_lineage(col_name: str, table_raw_cols: Set[str] = None) -> Dict[str, Any]:
    """
    Identifies feature lineage dynamically.
    If table_raw_cols is provided, any column not in initial raw schema is flagged as engineered.
    """
    name_lower = col_name.lower()
    
    if _detect_key_column(col_name):
        return {"lineage": "raw", "is_engineered": False, "parent_column": None}

    # Ground-truth dynamic check against original raw schema
    if table_raw_cols is not None:
        if col_name in table_raw_cols:
            return {"lineage": "raw", "is_engineered": False, "parent_column": None}
    else:
        # Fallback to standard set check if raw schema wasn't captured
        if name_lower in RAW_COLUMNS:
            return {"lineage": "raw", "is_engineered": False, "parent_column": None}

    # Baseline mathematical transformations
    if name_lower.endswith(("_log", "_squared", "_cubed", "_sqrt", "_boxcox", "_scaled", "_binned")):
        parent = col_name.rsplit("_", 1)[0]
        return {"lineage": "baseline_transformation", "is_engineered": True, "parent_column": parent}

    # Datetime component extractions
    dt_suffixes = ("_year", "_month", "_day", "_is_weekend", "_dayofweek", "_quarter", "_dayofyear", "_hour", "_days")
    if any(name_lower.endswith(s) for s in dt_suffixes) or name_lower.startswith(("recency_", "duration_")):
        parent = None
        for suffix in ("_year", "_month", "_day", "_is_weekend", "_dayofweek", "_quarter", "_dayofyear", "_hour"):
            if name_lower.endswith(suffix):
                parent = col_name[:-len(suffix)]
                break
        return {"lineage": "datetime_extraction", "is_engineered": True, "parent_column": parent}

    # LLM / Cross-file domain feature engineering
    return {"lineage": "llm_engineered", "is_engineered": True, "parent_column": None}


def _build_aligned_numeric_df(dataframes: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Merges numeric features from ALL active tables (transactions, customers, products, sessions, returns, search_logs, promotions)
    onto transactions (or largest table) to build a fully aligned numeric feature matrix.
    """
    txn = dataframes.get("transactions")
    if not isinstance(txn, pd.DataFrame) or txn.empty:
        largest_df = pd.DataFrame()
        for df in dataframes.values():
            if isinstance(df, pd.DataFrame) and len(df) > len(largest_df):
                largest_df = df
        return largest_df.select_dtypes(include=[np.number]).copy() if not largest_df.empty else pd.DataFrame()

    merged = txn.copy()
    
    # Iterate through all non-transaction tables and merge their numeric columns
    for table_name, df in dataframes.items():
        if table_name == "transactions" or not isinstance(df, pd.DataFrame) or df.empty:
            continue
            
        num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not _detect_key_column(c)]
        if not num_cols:
            continue
            
        possible_keys = [c for c in df.columns if _detect_key_column(c) and c in merged.columns]
        if not possible_keys:
            continue
            
        join_key = possible_keys[0]
        cols_to_merge = [c for c in num_cols if c not in merged.columns]
        if not cols_to_merge:
            continue
            
        if df[join_key].is_unique:
            merged = merged.merge(df[[join_key] + cols_to_merge], on=join_key, how="left")
        else:
            # 1-to-many relationship (e.g., returns, search logs) -> aggregate numeric stats per key
            agg_dict = {c: "mean" for c in cols_to_merge}
            aggregated = df.groupby(join_key).agg(agg_dict).reset_index()
            merged = merged.merge(aggregated, on=join_key, how="left")

    return merged.select_dtypes(include=[np.number]).copy()


def _filter_features_for_analysis(df: pd.DataFrame, raw_schema_sets: Dict[str, Set[str]] = None, max_cols: int = 20) -> List[str]:
    """
    Step 1 Filtering Algorithm:
    1. Excludes Key/ID columns.
    2. Excludes constant / zero-variance columns.
    3. Excludes columns with > 90% missing values.
    4. Handles paired features (prefers _log if raw is heavily skewed).
    5. Prioritizes target variables and highly informative / engineered features up to max_cols.
    """
    if df.empty:
        return []

    candidates = []
    
    for col in df.columns:
        if _detect_key_column(col):
            continue

        series = df[col].dropna()
        if len(series) < 2:
            continue

        unique_cnt = series.nunique()
        std_val = series.std()
        if unique_cnt <= 1 or pd.isna(std_val) or std_val == 0:
            continue

        null_ratio = df[col].isna().mean()
        if null_ratio > 0.90:
            continue

        candidates.append(col)

    # Paired Raw vs Transformed selection
    filtered_set = set(candidates)
    to_drop_from_charts = set()
    
    for col in candidates:
        lineage_meta = _detect_lineage(col)
        if lineage_meta["is_engineered"] and lineage_meta["parent_column"]:
            parent = lineage_meta["parent_column"]
            if parent in filtered_set and pd.api.types.is_numeric_dtype(df[parent]):
                raw_skew = df[parent].dropna().skew() if len(df[parent].dropna()) > 10 else 0.0
                if abs(raw_skew) <= 0.75:
                    to_drop_from_charts.add(col)
                else:
                    to_drop_from_charts.add(parent)

    candidates = [c for c in candidates if c not in to_drop_from_charts]

    # Correlation / Multicollinearity filtering to eliminate redundant features (r > 0.85)
    if len(candidates) > 1:
        num_sub = df[candidates].select_dtypes(include=[np.number])
        if not num_sub.empty and num_sub.shape[1] > 1:
            corr = num_sub.corr().abs()
            cols_to_keep = list(candidates)
            for i in range(len(candidates)):
                c1 = candidates[i]
                if c1 not in cols_to_keep or c1 not in corr.columns:
                    continue
                for j in range(i + 1, len(candidates)):
                    c2 = candidates[j]
                    if c2 not in cols_to_keep or c2 not in corr.columns:
                        continue
                    r_val = corr.loc[c1, c2]
                    if not np.isnan(r_val) and r_val > 0.85:
                        sk1 = abs(df[c1].dropna().skew()) if len(df[c1].dropna()) > 5 else 0.0
                        sk2 = abs(df[c2].dropna().skew()) if len(df[c2].dropna()) > 5 else 0.0
                        dropped = c1 if sk1 > sk2 else c2
                        if dropped in cols_to_keep:
                            cols_to_keep.remove(dropped)
            candidates = cols_to_keep

    # Target variable identification & priority boosting
    TARGET_NAMES = {"amount", "price", "quantity", "total_spend", "revenue", "rating", "purchased", "is_return", "total_revenue", "avg_order_value", "total_units_sold"}
    
    # Informative Scoring incorporating Variance, Skewness Balance, Completeness & Layer 1 Lineage
    scored_features = []
    for col in candidates:
        series = df[col].dropna()
        lineage_meta = _detect_lineage(col)
        
        score = 1.0
        # Criterion 1: Target / Key Business Metrics Boost (+2.5)
        if any(kw in col.lower() for kw in TARGET_NAMES):
            score += 2.5
        
        # Criterion 2: Layer 1 Engineered Features Boost (+1.5)
        if lineage_meta["is_engineered"]:
            score += 1.5

        # Criterion 3: Variance & Information Density Score (std & Coefficient of Variation)
        std_val = float(series.std()) if len(series) > 1 else 0.0
        mean_val = float(series.mean()) if len(series) > 0 else 0.0
        cv_val = std_val / (abs(mean_val) + 1e-5) if mean_val != 0 else std_val
        score += min(cv_val * 0.1, 1.0)

        # Criterion 4: Completeness & Value Diversity Score
        null_pct = df[col].isna().mean()
        score += (1.0 - null_pct) * 0.5
        if series.nunique() > 5:
            score += 0.3

        # Domain Tagging for Round-Robin Stratified Selection
        c_lower = col.lower()
        if any(k in c_lower for k in ["price", "spend", "revenue", "amount", "cost", "value"]):
            domain = "monetary"
        elif any(k in c_lower for k in ["year", "month", "day", "weekend", "hour", "date", "recency"]):
            domain = "temporal"
        elif any(k in c_lower for k in ["units", "sold", "demand", "category", "prod", "item"]):
            domain = "volume"
        else:
            domain = "behavioral"

        scored_features.append({"col": col, "score": score, "domain": domain})

    scored_features.sort(key=lambda x: x["score"], reverse=True)

    # Domain Stratified Round-Robin Selection to guarantee Domain Diversity
    domain_groups = {}
    for item in scored_features:
        domain_groups.setdefault(item["domain"], []).append(item["col"])

    final_cols = []
    added = set()
    
    # Stratified Round-Robin pull from each domain
    while len(final_cols) < max_cols and len(added) < len(scored_features):
        progress = False
        for dom, cols in domain_groups.items():
            for c in cols:
                if c not in added:
                    final_cols.append(c)
                    added.add(c)
                    progress = True
                    break
            if len(final_cols) >= max_cols:
                break
        if not progress:
            break

    return final_cols[:max_cols]


def _sanitize_dict_for_json(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _sanitize_dict_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_dict_for_json(v) for v in obj]
    elif isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    elif isinstance(obj, (float, np.floating)):
        val = float(obj)
        if np.isnan(val) or np.isinf(val):
            return 0.0
        return val
    elif isinstance(obj, (int, np.integer)):
        return int(obj)
    elif pd.isna(obj):
        return None
    return obj


def _detect_column(df: pd.DataFrame, keywords: List[str]) -> str:
    for col in df.columns:
        if any(kw in col.lower() for kw in keywords):
            return col
    return None


def category_breakdown(txn: pd.DataFrame, products: pd.DataFrame, category_key: str) -> List[Dict[str, Any]]:
    if "product_id" in txn.columns and "product_id" in products.columns and category_key in products.columns:
        merged = txn.merge(products[["product_id", category_key]], on="product_id", how="left")
        counts = merged.groupby(category_key).size().sort_values(ascending=False)
        return [{"category": str(k), "count": int(c)} for k, c in counts.items()]
    return []


def segment_breakdown(txn: pd.DataFrame, customers: pd.DataFrame, segment_key: str) -> List[Dict[str, Any]]:
    if "customer_id" in txn.columns and "customer_id" in customers.columns and segment_key in customers.columns:
        merged = txn.merge(customers[["customer_id", segment_key]], on="customer_id", how="left")
        counts = merged.groupby(segment_key).size().sort_values(ascending=False)
        return [{"segment": str(k), "count": int(c)} for k, c in counts.items()]
    return []


def _top_products(txn: pd.DataFrame, top_n: int = 10) -> List[Dict[str, Any]]:
    if "product_id" in txn.columns:
        counts = txn.groupby("product_id").size().sort_values(ascending=False).head(top_n)
        return [{"product_id": str(p), "count": int(c)} for p, c in counts.items()]
    return []


def _generate_action_suggestion(series: pd.Series, is_num: bool, col_name: str, is_key: bool, df: pd.DataFrame = None, table_raw_cols: Set[str] = None) -> str:
    """Generates executable deterministic recommendations based on EDA findings."""
    if is_key:
        return "Identifier key column — excluded from statistical modeling."
    
    null_ratio = series.isna().mean()
    if null_ratio > 0.40:
        return f"High missingness ({null_ratio:.0%}) — impute with median or drop column."
    
    if is_num:
        non_null = series.dropna()
        std_val = non_null.std() if len(non_null) > 1 else 0
        if std_val == 0 or non_null.nunique() <= 1:
            return "Zero variance constant feature — recommend dropping to prevent redundancy."
            
        lineage_meta = _detect_lineage(col_name, table_raw_cols=table_raw_cols)
        if lineage_meta["is_engineered"]:
            if lineage_meta["parent_column"] and df is not None and lineage_meta["parent_column"] in df.columns:
                parent = lineage_meta["parent_column"]
                if pd.api.types.is_numeric_dtype(df[parent]):
                    parent_series = df[parent].dropna()
                    parent_skew = parent_series.skew() if len(parent_series) > 10 else 0.0
                    if abs(parent_skew) <= 0.75:
                        return f"Redundant transformation — parent feature '{parent}' is already balanced (skew={parent_skew:.2f}). Recommend dropping."

            if len(non_null) > 10:
                skew = non_null.skew()
                if skew > 0.75:
                    return f"Engineered feature exhibits positive skewness ({skew:.2f}) — power_transform (Yeo-Johnson) recommended."
                elif skew < -0.75:
                    return f"Engineered feature exhibits negative skewness ({skew:.2f}) — power_transform or quantile_transform recommended."

        if df is not None and f"{col_name}_log" in df.columns:
            if len(non_null) > 10:
                raw_skew = non_null.skew()
                if abs(raw_skew) > 0.75:
                    return f"High raw skewness ({raw_skew:.2f}) — replace with '{col_name}_log' for model ingestion."

        if len(non_null) > 10:
            skew = non_null.skew()
            if skew > 0.75:
                return f"High positive skewness ({skew:.2f}) — log_transform recommended."
            elif skew < -0.75:
                return f"High negative skewness ({skew:.2f}) — square_transform or log_transform recommended."
            
        return "Balanced numeric distribution (|skew| <= 0.75) — ready for model ingestion."
    
    return "Categorical feature — suitable for group aggregations."


def _compute_column_stats(dataframes: Dict[str, pd.DataFrame], raw_schema_sets: Dict[str, Set[str]] = None, selected_chart_features: Set[str] = None) -> List[Dict[str, Any]]:
    stats = []

    for name, df in dataframes.items():
        if not isinstance(df, pd.DataFrame):
            continue
        table_raw_cols = raw_schema_sets.get(name) if raw_schema_sets else None

        # Pre-compute pairwise correlation for collinearity detection within dataset
        num_df = df.select_dtypes(include=[np.number])
        corr_partner_map = {}
        if not num_df.empty and num_df.shape[1] > 1:
            try:
                corr = num_df.corr()
                for i, c1 in enumerate(corr.columns):
                    if c1 in corr_partner_map:
                        continue
                    for j in range(i + 1, len(corr.columns)):
                        c2 = corr.columns[j]
                        if c2 in corr_partner_map:
                            continue
                        r_val = corr.loc[c1, c2]
                        if not np.isnan(r_val) and abs(r_val) > 0.95:
                            sk1 = abs(df[c1].dropna().skew()) if len(df[c1].dropna()) > 5 else 0.0
                            sk2 = abs(df[c2].dropna().skew()) if len(df[c2].dropna()) > 5 else 0.0
                            dropped_col, kept_col = (c1, c2) if sk1 > sk2 else (c2, c1)
                            corr_partner_map[dropped_col] = (kept_col, float(r_val))
            except Exception:
                pass

        for col in df.columns:
            series = df[col]
            is_num = bool(pd.api.types.is_numeric_dtype(series))
            is_key = bool(_detect_key_column(col))

            # Drop all non-numeric / categorical features from Feature Quality Audit Table as requested
            if not is_num:
                continue

            lineage_meta = _detect_lineage(col, table_raw_cols=table_raw_cols)
            non_null = series.dropna()
            is_constant = bool((len(non_null) > 0 and non_null.nunique() <= 1) or (is_num and len(non_null) > 1 and non_null.std() == 0))

            # Determine feature retention status & detailed drop reason naming partner column
            if is_key:
                status = "dropped"
                drop_reason = "Identifier Key Column"
            elif is_constant:
                status = "dropped"
                drop_reason = "Zero Variance / Constant Feature"
            elif f"{col}_log" in df.columns and len(non_null) > 10 and abs(non_null.skew()) > 0.75:
                status = "dropped"
                drop_reason = f"Raw Skewed ({non_null.skew():.2f}) -> Replaced by '{col}_log'"
            elif col in corr_partner_map:
                partner, r_val = corr_partner_map[col]
                status = "dropped"
                drop_reason = f"High Correlation (r = {r_val:.2f}) with '{partner}'"
            elif len(non_null) > 10 and non_null.nunique() > 2 and abs(non_null.skew()) > 0.75:
                status = "dropped"
                drop_reason = f"High Skewness ({non_null.skew():.2f}) -> Exceeds balance threshold (|skew| > 0.75)"
            elif lineage_meta["is_engineered"] and lineage_meta["parent_column"] and lineage_meta["parent_column"] in df.columns:
                parent = lineage_meta["parent_column"]
                if pd.api.types.is_numeric_dtype(df[parent]) and len(df[parent].dropna()) > 10 and abs(df[parent].dropna().skew()) <= 0.75:
                    status = "dropped"
                    drop_reason = f"Redundant Transformation -> Parent '{parent}' is balanced"
                else:
                    status = "retained"
                    drop_reason = None
            else:
                status = "retained"
                drop_reason = None

            stat_item = {
                "dataset": str(name).upper(),
                "column_name": str(col),
                "dtype": str(series.dtype),
                "null_count": int(series.isna().sum()),
                "unique_count": int(series.nunique(dropna=True)),
                "is_numeric": is_num,
                "is_key": is_key,
                "is_constant": is_constant,
                "status": status,
                "drop_reason": drop_reason,
                "lineage": str(lineage_meta["lineage"]),
                "is_engineered": bool(lineage_meta["is_engineered"]),
                "parent_column": str(lineage_meta["parent_column"]) if lineage_meta["parent_column"] else None,
                "action_suggestion": str(_generate_action_suggestion(series, is_num, col, is_key, df, table_raw_cols=table_raw_cols))
            }
            
            if is_num:
                stat_item.update({
                    "mean": round(float(non_null.mean()), 2) if len(non_null) > 0 else 0.0,
                    "std": round(float(non_null.std()), 2) if len(non_null) > 0 else 0.0,
                    "median": round(float(non_null.median()), 2) if len(non_null) > 0 else 0.0,
                    "skewness": round(float(non_null.skew()), 2) if len(non_null) > 10 else 0.0,
                    "min": round(float(non_null.min()), 2) if len(non_null) > 0 else 0.0,
                    "max": round(float(non_null.max()), 2) if len(non_null) > 0 else 0.0,
                })
            stats.append(stat_item)
    return stats


def _compute_numeric_distributions(num_df: pd.DataFrame, max_cols: int = 20) -> Dict[str, Any]:
    distributions = {}
    if num_df.empty:
        return distributions
        
    for col in num_df.columns[:max_cols]:
        series = num_df[col].dropna()
        if len(series) > 5 and series.nunique() > 1:
            try:
                counts, edges = pd.cut(series, bins=8, retbins=True, duplicates="drop")
                hist = counts.value_counts().sort_index()
                bins_data = [
                    {"range": f"{interval.left:.1f} - {interval.right:.1f}", "count": int(c)}
                    for interval, c in hist.items()
                ]
                # Add per-feature summary stats for the distribution view
                skew_val = float(series.skew()) if len(series) > 10 else 0.0
                distributions[col] = {
                    "bins": bins_data,
                    "mean": round(float(series.mean()), 2),
                    "median": round(float(series.median()), 2),
                    "std": round(float(series.std()), 2),
                    "skewness": round(skew_val, 2),
                    "min": round(float(series.min()), 2),
                    "max": round(float(series.max()), 2),
                }
            except Exception:
                continue
    return distributions


def _compute_correlation_matrix(num_df: pd.DataFrame, max_cols: int = 20) -> Dict[str, Any]:
    if num_df.empty or len(num_df.columns) < 2:
        return {"columns": [], "matrix": []}
    
    target_cols = list(num_df.columns[:max_cols])
    corr_df = num_df[target_cols].fillna(0).corr().round(2)
    corr_df = corr_df.fillna(0.0).replace([np.inf, -np.inf], 0.0)
    
    return {
        "columns": target_cols,
        "matrix": corr_df.values.tolist()
    }


def _compute_categorical_breakdowns(txn: pd.DataFrame, products: pd.DataFrame) -> Dict[str, Any]:
    breakdowns = {}
    if txn.empty:
        return breakdowns
    combined_df = txn.copy()
    if not products.empty and "product_id" in txn.columns and "product_id" in products.columns:
        extra_cols = [c for c in products.columns if c not in txn.columns and c != "product_id"]
        if extra_cols:
            combined_df = combined_df.merge(products[["product_id"] + extra_cols], on="product_id", how="left")
            
    for col in combined_df.columns:
        if not _detect_key_column(col) and combined_df[col].nunique() <= 15 and combined_df[col].nunique() > 1:
            counts = combined_df[col].value_counts(dropna=False).head(10)
            breakdowns[col] = [{"label": str(k), "count": int(v)} for k, v in counts.items()]
            
    return breakdowns


def _transactions_over_time(txn: pd.DataFrame) -> List[Dict[str, Any]]:
    if txn.empty:
        return []
    date_col = next((c for c in txn.columns if "date" in c.lower() or "time" in c.lower()), None)
    if not date_col:
        return []
        
    dt_series = pd.to_datetime(txn[date_col], errors="coerce")
    valid = txn.dropna(subset=[date_col])
    if valid.empty:
        return []
    weekly = valid.set_index(pd.DatetimeIndex(dt_series.dropna())).resample("W").size()
    return [{"period": str(d.date()), "count": int(c)} for d, c in weekly.items()]


def _sparsity(txn: pd.DataFrame, customers: pd.DataFrame, products: pd.DataFrame) -> float:
    if "customer_id" not in customers or "product_id" not in products:
        return 1.0
    n_cust = customers["customer_id"].nunique()
    n_prod = products["product_id"].nunique()
    if n_cust == 0 or n_prod == 0:
        return 1.0
    n_interactions = txn[["customer_id", "product_id"]].drop_duplicates().shape[0] if "customer_id" in txn and "product_id" in txn else 0
    return round(1.0 - (n_interactions / (n_cust * n_prod)), 4)


def _compute_scatterplots(num_df: pd.DataFrame, max_pairs: int = 8, sample_n: int = 500) -> List[Dict[str, Any]]:
    """Generate scatterplot data for interesting feature pairs.
    Uses PAIRWISE dropna (not global) so NaN in unrelated columns doesn't kill data.
    Includes ALL pairs sorted by correlation interest — not restricted to 0.15-0.85 band."""
    if num_df.empty or num_df.shape[1] < 2:
        return []

    # Filter to numeric non-key columns
    numeric_cols = [c for c in num_df.columns if pd.api.types.is_numeric_dtype(num_df[c]) and not _detect_key_column(c)]
    if len(numeric_cols) < 2:
        return []

    # Compute pairwise correlation on full data (fillna is fine for correlation)
    try:
        corr = num_df[numeric_cols].corr().abs()
    except Exception:
        return []

    # Collect ALL non-self pairs, sorted by how interesting they are
    pairs = []
    seen = set()
    for i in range(len(numeric_cols)):
        for j in range(i + 1, len(numeric_cols)):
            c1, c2 = numeric_cols[i], numeric_cols[j]
            if c1 not in corr.columns or c2 not in corr.columns:
                continue
            r = corr.loc[c1, c2]
            if np.isnan(r):
                continue
            # Skip near-perfect collinear pairs (r > 0.95) — redundant
            if r > 0.95:
                continue
            pairs.append(((c1, c2), float(r)))
            seen.add((c1, c2))

    # Also add key business pairs if not already present
    business_pairs = [
        ("price", "quantity"), ("price", "total_amount"), ("quantity", "total_amount"),
        ("price", "total_spend"), ("quantity", "total_units_sold"),
        ("revenue_per_unit", "avg_order_value"), ("total_units_sold", "revenue_per_unit"),
    ]
    for bp in business_pairs:
        if bp[0] in numeric_cols and bp[1] in numeric_cols and bp not in seen and (bp[1], bp[0]) not in seen:
            try:
                r = float(corr.loc[bp[0], bp[1]])
                if not np.isnan(r):
                    pairs.append((bp, r))
                    seen.add(bp)
            except (KeyError, ValueError):
                continue

    # Sort: prefer pairs with moderate-to-strong correlation (0.2-0.85), then others
    def interest_score(r):
        if 0.2 <= r <= 0.85:
            return 1.0 + r  # highest interest
        return r  # still include but lower priority

    pairs.sort(key=lambda x: interest_score(x[1]), reverse=True)
    pairs = pairs[:max_pairs]

    scatterplots = []
    for (x_col, y_col), r_val in pairs:
        # PAIRWISE dropna — only drop rows where THIS pair has NaN
        pair_df = num_df[[x_col, y_col]].dropna()
        if pair_df.empty or len(pair_df) < 5:
            continue

        # Sample for performance
        if len(pair_df) > sample_n:
            pair_df = pair_df.sample(n=sample_n, random_state=42)

        point_list = []
        for _, row in pair_df.iterrows():
            xv = float(row[x_col])
            yv = float(row[y_col])
            if np.isnan(xv) or np.isinf(xv) or np.isnan(yv) or np.isinf(yv):
                continue
            point_list.append({"x": round(xv, 4), "y": round(yv, 4)})
        if point_list:
            scatterplots.append({
                "x_feature": x_col,
                "y_feature": y_col,
                "correlation": round(r_val, 3),
                "n_points": len(point_list),
                "points": point_list,
            })
    return scatterplots


def _compute_overview_stats(dataframes: Dict[str, pd.DataFrame], aligned_df: pd.DataFrame,
                            summary: Dict[str, Any]) -> Dict[str, Any]:
    """Compute additional overview dashboard stats: data quality, feature counts, avg metrics."""
    txn = dataframes.get("transactions", pd.DataFrame())
    customers = dataframes.get("customers", pd.DataFrame())
    products = dataframes.get("products", pd.DataFrame())

    stats = {}

    # Data quality score (0-100): based on missingness, duplicates, type consistency
    if not txn.empty:
        null_pct = txn.isnull().mean().mean() if not txn.empty else 0
        dup_pct = txn.duplicated().mean() if not txn.empty else 0
        stats["data_quality_score"] = round(max(0, (1 - null_pct * 2 - dup_pct) * 100), 1)
        stats["total_null_pct"] = round(float(null_pct * 100), 2)
        stats["duplicate_txn_pct"] = round(float(dup_pct * 100), 2)
    else:
        stats["data_quality_score"] = 0
        stats["total_null_pct"] = 0
        stats["duplicate_txn_pct"] = 0

    # Feature counts
    col_stats = summary.get("column_stats", [])
    stats["n_retained_features"] = len([c for c in col_stats if c.get("status") == "retained"])
    stats["n_dropped_features"] = len([c for c in col_stats if c.get("status") == "dropped"])
    stats["n_engineered_features"] = len([c for c in col_stats if c.get("is_engineered")])
    stats["n_total_columns"] = sum(len(df.columns) for df in dataframes.values() if isinstance(df, pd.DataFrame))
    stats["n_numeric_features"] = aligned_df.shape[1] if not aligned_df.empty else 0

    # Business metrics
    if "price" in txn.columns:
        stats["avg_price"] = round(float(txn["price"].mean()), 2)
        stats["median_price"] = round(float(txn["price"].median()), 2)
    if "quantity" in txn.columns:
        stats["avg_quantity"] = round(float(txn["quantity"].mean()), 2)
    if "price" in txn.columns and "quantity" in txn.columns:
        stats["avg_order_value"] = round(float((txn["price"] * txn["quantity"]).mean()), 2)
        stats["total_revenue"] = round(float((txn["price"] * txn["quantity"]).sum()), 2)

    # Avg transactions per customer
    if "customer_id" in txn.columns:
        stats["avg_txn_per_customer"] = round(float(txn.groupby("customer_id").size().mean()), 1)
        stats["max_txn_per_customer"] = int(txn.groupby("customer_id").size().max())

    # Active files
    stats["active_tables"] = [k for k, v in dataframes.items() if isinstance(v, pd.DataFrame) and not v.empty]

    return stats


def _generate_insights(summary: Dict[str, Any], chart_df: pd.DataFrame) -> Dict[str, List[str]]:
    """Auto-generate textual insights for each EDA section."""
    insights: Dict[str, List[str]] = {}

    # ── Overview Insights ──
    overview = []
    n_txn = summary.get("n_transactions", 0)
    n_cust = summary.get("n_customers", 0)
    n_prod = summary.get("n_products", 0)
    sparsity = summary.get("sparsity", 0)

    overview.append(f"Dataset contains {n_txn:,} transactions across {n_cust:,} customers and {n_prod:,} products.")
    if sparsity:
        if sparsity > 0.95:
            overview.append(f"Interaction matrix sparsity is {sparsity:.1%} — very sparse, cold-start handling recommended.")
        elif sparsity > 0.8:
            overview.append(f"Interaction matrix sparsity is {sparsity:.1%} — moderate sparsity, collaborative filtering viable.")
        else:
            overview.append(f"Interaction matrix sparsity is {sparsity:.1%} — relatively dense, good signal quality.")

    col_stats = summary.get("column_stats", [])
    retained = [c for c in col_stats if c.get("status") == "retained"]
    dropped = [c for c in col_stats if c.get("status") == "dropped"]
    if retained or dropped:
        overview.append(f"Feature audit identified {len(retained)} retained and {len(dropped)} dropped features for modelling.")

    # Drop reason breakdown
    drop_reasons = {}
    for d in dropped:
        reason = (d.get("drop_reason") or "Unknown").split("(")[0].split("->")[0].strip()
        drop_reasons[reason] = drop_reasons.get(reason, 0) + 1
    if drop_reasons:
        parts = [f"{v} for {k.lower()}" for k, v in drop_reasons.items()]
        overview.append(f"Drop breakdown: {'; '.join(parts)}.")

    selected = summary.get("selected_chart_features", [])
    if selected:
        overview.append(f"Top {len(selected)} chart features selected for distribution & correlation analysis: {', '.join(selected)}.")

    insights["overview"] = overview

    # ── Correlation Insights ──
    corr_insights = []
    corr_data = summary.get("correlation_matrix", {})
    corr_cols = corr_data.get("columns", [])
    corr_matrix = corr_data.get("matrix", [])

    if corr_cols and corr_matrix:
        strong_pairs = []
        moderate_pairs = []
        seen_pairs = set()
        for i in range(len(corr_cols)):
            for j in range(i + 1, len(corr_cols)):
                try:
                    r = corr_matrix[i][j]
                except (IndexError, TypeError):
                    continue
                pair_key = tuple(sorted([corr_cols[i], corr_cols[j]]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                if abs(r) > 0.7:
                    strong_pairs.append((corr_cols[i], corr_cols[j], r))
                elif abs(r) > 0.4:
                    moderate_pairs.append((corr_cols[i], corr_cols[j], r))

        if strong_pairs:
            corr_insights.append(f"Found {len(strong_pairs)} strongly correlated pair(s) (|r| > 0.7) among chart features.")
            for x, y, v in strong_pairs[:3]:
                direction = "positive" if v > 0 else "negative"
                corr_insights.append(f"  • {x} ↔ {y}: r = {v:+.2f} ({direction})")
        if moderate_pairs:
            corr_insights.append(f"Found {len(moderate_pairs)} moderately correlated pair(s) (0.4 < |r| < 0.7).")
        if not strong_pairs and not moderate_pairs:
            corr_insights.append("Chart features show low mutual correlation — good feature independence for modelling.")

    insights["correlation"] = corr_insights

    # ── Distribution Insights ──
    dist_insights = []
    dist_data = summary.get("numeric_distributions", {})
    for feat_name, feat_info in dist_data.items():
        if isinstance(feat_info, dict):
            skew = feat_info.get("skewness", 0)
        else:
            skew = 0
        if abs(skew) > 2.0:
            dist_insights.append(f"{feat_name} is highly skewed (skew={skew:.2f}) — log/power transform recommended before modelling.")
        elif abs(skew) > 1.0:
            dist_insights.append(f"{feat_name} shows moderate skewness (skew={skew:.2f}) — monitor for model sensitivity.")

    if not dist_insights:
        dist_insights.append("All selected chart features have acceptable distribution shapes for modelling.")
    insights["distribution"] = dist_insights

    return insights
