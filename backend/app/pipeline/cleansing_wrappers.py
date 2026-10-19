"""
Deterministic Data Cleansing, Transformation & Feature Engineering Wrappers.

Contains standard, robust pandas execution functions used by the Rule Executor
for deterministic baseline operations across retail datasets.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List


# =========================================================
# 1. IMPUTATION WRAPPERS (NULL HANDLING)
# =========================================================

def impute_median(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Fills missing numeric values with the column median."""
    if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
        df[col] = df[col].fillna(df[col].median())
    return df


def impute_mean(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Fills missing numeric values with the column mean."""
    if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
        df[col] = df[col].fillna(df[col].mean())
    return df


def impute_mode(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Fills missing categorical/string values with the column mode."""
    if col in df.columns:
        mode_series = df[col].mode()
        if not mode_series.empty:
            df[col] = df[col].fillna(mode_series.iloc[0])
    return df


def impute_constant(df: pd.DataFrame, col: str, fill_value: Any = "Unknown") -> pd.DataFrame:
    """Fills missing values with a fixed constant."""
    if col in df.columns:
        df[col] = df[col].fillna(fill_value)
    return df


# =========================================================
# 2. TRANSFORMATION WRAPPERS (SKEWNESS & OUTLIERS)
# =========================================================

def log_transform(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Applies log1p transform to handle right-skewed numeric columns."""
    if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
        min_val = df[col].min()
        shift = abs(min_val) + 1.0 if min_val < 0 else 1.0
        df[f"{col}_log"] = np.log1p(df[col] + (shift - 1.0))
    return df


def square_transform(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Applies square transform (x^2) to handle left-skewed numeric columns (e.g. ratings)."""
    if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
        df[f"{col}_squared"] = df[col] ** 2
    return df


def cap_outliers_iqr(df: pd.DataFrame, col: str, factor: float = 1.5) -> pd.DataFrame:
    """Caps numeric outliers outside 1.5 * IQR bounds."""
    if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
        q1 = df[col].quantile(0.25)
        q3 = df[col].quantile(0.75)
        iqr = q3 - q1
        df[col] = df[col].clip(lower=q1 - factor * iqr, upper=q3 + factor * iqr)
    return df


def cap_outliers_zscore(df: pd.DataFrame, col: str, threshold: float = 3.0) -> pd.DataFrame:
    """Caps numeric outliers outside mean +/- threshold * std (Z-score 3-sigma capping)."""
    if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
        mean_val = df[col].mean()
        std_val = df[col].std()
        if std_val > 0:
            lower_bound = mean_val - threshold * std_val
            upper_bound = mean_val + threshold * std_val
            df[col] = df[col].clip(lower=lower_bound, upper=upper_bound)
    return df


def cap_outliers_percentile(df: pd.DataFrame, col: str, lower_pct: float = 0.01, upper_pct: float = 0.99) -> pd.DataFrame:
    """Winsorizes numeric values by capping below lower_pct and above upper_pct (1st-99th percentile)."""
    if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
        lower_bound = df[col].quantile(lower_pct)
        upper_bound = df[col].quantile(upper_pct)
        df[col] = df[col].clip(lower=lower_bound, upper=upper_bound)
    return df


# =========================================================
# 3. ENCODING WRAPPERS
# =========================================================

def one_hot_encode(df: pd.DataFrame, col: str, max_categories: int = 10) -> pd.DataFrame:
    """Performs one-hot encoding for low cardinality categoricals."""
    if col in df.columns:
        top_cats = df[col].value_counts().nlargest(max_categories).index
        for cat in top_cats:
            cat_str = str(cat).replace(" ", "_").lower()
            df[f"{col}_{cat_str}"] = (df[col] == cat).astype(int)
    return df


def label_encode(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Encodes categorical strings into integer labels."""
    if col in df.columns:
        df[f"{col}_encoded"] = df[col].astype("category").cat.codes
    return df


def frequency_encode(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Replaces categorical values with their frequency ratio."""
    if col in df.columns:
        freq_map = df[col].value_counts(normalize=True).to_dict()
        df[f"{col}_freq"] = df[col].map(freq_map).fillna(0.0)
    return df


# =========================================================
# 4. DATETIME PARSING & TIME FEATURES
# =========================================================

def parse_datetime_features(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Parses date/time strings and extracts temporal features."""
    if col in df.columns:
        dt_series = pd.to_datetime(df[col], errors="coerce")
        df[f"{col}_year"] = dt_series.dt.year.fillna(0).astype(int)
        df[f"{col}_month"] = dt_series.dt.month.fillna(0).astype(int)
        df[f"{col}_day"] = dt_series.dt.day.fillna(0).astype(int)
        df[f"{col}_dayofweek"] = dt_series.dt.dayofweek.fillna(0).astype(int)
        df[f"{col}_is_weekend"] = dt_series.dt.dayofweek.isin([5, 6]).astype(int)
        if dt_series.dt.hour.nunique() > 1:
            df[f"{col}_hour"] = dt_series.dt.hour.fillna(0).astype(int)
    return df


# =========================================================
# 5. SINGLE-FILE SURE-SHOT FEATURE ENGINEERING WRAPPERS
# =========================================================

def compute_total_amount(df: pd.DataFrame, price_col: str, qty_col: str) -> pd.DataFrame:
    """Computes total_amount = price * quantity within transactions table."""
    if price_col in df.columns and qty_col in df.columns:
        df["total_amount"] = df[price_col] * df[qty_col]
    return df


def bin_customer_age(df: pd.DataFrame, col: str = "age") -> pd.DataFrame:
    """Bins numeric customer age into standard age group categories."""
    if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
        bins = [-1, 18, 25, 35, 50, 120]
        labels = ["<18", "18-24", "25-34", "35-49", "50+"]
        df["age_group"] = pd.cut(df[col], bins=bins, labels=labels)
    return df


def bin_price_tiers(df: pd.DataFrame, col: str = "price") -> pd.DataFrame:
    """Bins product prices into 3 quantile price tiers: budget, mid_tier, premium."""
    if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
        try:
            df["price_tier"] = pd.qcut(df[col], q=3, labels=["budget", "mid_tier", "premium"])
        except ValueError:
            df["price_tier"] = "mid_tier"
    return df


def compute_discount_percentage(df: pd.DataFrame, mrp_col: str, sale_col: str) -> pd.DataFrame:
    """Computes discount percentage = (mrp - sale_price) / mrp * 100."""
    if mrp_col in df.columns and sale_col in df.columns:
        mrp_series = df[mrp_col].replace(0, np.nan)
        df["discount_pct"] = ((df[mrp_col] - df[sale_col]) / mrp_series * 100).fillna(0.0)
    return df


def compute_account_tenure(df: pd.DataFrame, signup_date_col: str) -> pd.DataFrame:
    """Computes account tenure in days from signup_date."""
    if signup_date_col in df.columns:
        dt_series = pd.to_datetime(df[signup_date_col], errors="coerce")
        max_dt = dt_series.max() or pd.Timestamp.now()
        df["account_tenure_days"] = (max_dt - dt_series).dt.days.fillna(0).astype(int)
    return df


def compute_session_bounce(df: pd.DataFrame, pages_viewed_col: str) -> pd.DataFrame:
    """Flags single-page bounce sessions (pages_viewed == 1)."""
    if pages_viewed_col in df.columns:
        df["is_bounce"] = (df[pages_viewed_col] == 1).astype(int)
    return df


# =========================================================
# 6. DYNAMIC CROSS-FILE BASELINE AGGREGATIONS (MULTIPLE FILES)
# =========================================================

def _detect_file_by_keywords(dfs: Dict[str, pd.DataFrame], keywords: List[str]) -> str:
    """Helper to detect a dataframe in dfs by checking filename or column keywords."""
    for key, df in dfs.items():
        k_lower = key.lower()
        if any(kw in k_lower for kw in keywords):
            return key
        cols_lower = [str(c).lower() for c in df.columns]
        if any(kw in col for col in cols_lower for kw in keywords):
            return key
    return None


def safe_fillna(df: pd.DataFrame, fill_val: Any = 0) -> pd.DataFrame:
    """Safely fills null values across all DataFrame columns without throwing Categorical setitem errors."""
    df_out = df.copy()
    for col in df_out.columns:
        if isinstance(df_out[col].dtype, pd.CategoricalDtype):
            df_out[col] = df_out[col].astype(object).fillna(fill_val)
        else:
            df_out[col] = df_out[col].fillna(fill_val)
    return df_out


def aggregate_cross_file_baseline(dfs: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """
    Computes sure-shot cross-file metrics (total spend, order count, return count)
    when multiple files (e.g. customers, transactions, products, returns) are present.
    """
    cust_key = _detect_file_by_keywords(dfs, ["cust", "user", "client"])
    tx_key = _detect_file_by_keywords(dfs, ["trans", "order", "buy"])
    prod_key = _detect_file_by_keywords(dfs, ["prod", "item", "article", "sku"])

    # 1. Customer Spend & Order Aggregations
    if cust_key and tx_key and cust_key in dfs and tx_key in dfs:
        cust_df, tx_df = dfs[cust_key], dfs[tx_key]
        user_col = next((c for c in cust_df.columns if any(k in c.lower() for k in ["cust", "user"])), None)
        price_col = next((c for c in tx_df.columns if any(k in c.lower() for k in ["price", "amount", "spend"])), None)

        if user_col and user_col in tx_df.columns and price_col:
            stats = tx_df.groupby(user_col).agg(
                total_spend=(price_col, "sum"),
                total_transactions=(price_col, "count"),
                avg_order_value=(price_col, "mean")
            ).reset_index()
            overlap_cols = [c for c in stats.columns if c != user_col and c in cust_df.columns]
            if overlap_cols:
                cust_df = cust_df.drop(columns=overlap_cols)
            dfs[cust_key] = safe_fillna(cust_df.merge(stats, on=user_col, how="left"), 0)

    # 2. Product Volume & Revenue Aggregations
    if prod_key and tx_key and prod_key in dfs and tx_key in dfs:
        prod_df, tx_df = dfs[prod_key], dfs[tx_key]
        item_col = next((c for c in prod_df.columns if any(k in c.lower() for k in ["item", "prod", "sku"])), None)
        price_col = next((c for c in tx_df.columns if any(k in c.lower() for k in ["price", "amount"])), None)
        qty_col = next((c for c in tx_df.columns if any(k in c.lower() for k in ["qty", "quantity"])), None)

        if item_col and item_col in tx_df.columns:
            agg_dict = {}
            if qty_col: agg_dict["total_units_sold"] = (qty_col, "sum")
            if price_col: agg_dict["total_product_revenue"] = (price_col, "sum")

            if agg_dict:
                stats = tx_df.groupby(item_col).agg(**agg_dict).reset_index()
                overlap_cols = [c for c in stats.columns if c != item_col and c in prod_df.columns]
                if overlap_cols:
                    prod_df = prod_df.drop(columns=overlap_cols)
                dfs[prod_key] = safe_fillna(prod_df.merge(stats, on=item_col, how="left"), 0)

    return dfs
