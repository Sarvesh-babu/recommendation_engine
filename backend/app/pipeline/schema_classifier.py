"""
Deterministic Schema Classifier for Retail Recommendation Datasets.

Classifies dataset columns deterministically using column names, pandas dtypes,
cardinalities, skewness, and regex patterns before calling the LLM.
"""

import re
import pandas as pd
import numpy as np
from typing import Dict, Any, List


# Regex patterns for deterministic matching
ID_PATTERN = re.compile(r'^(.*_)?(id|uuid|guid|code|sku|upc|barcode|index|no)$', re.IGNORECASE)
USER_ID_PATTERN = re.compile(r'^(user|cust|customer|client|member|account)_?id$', re.IGNORECASE)
ITEM_ID_PATTERN = re.compile(r'^(item|prod|product|article|asin|sku|goods)_?id$', re.IGNORECASE)
TIME_PATTERN = re.compile(r'(date|time|timestamp|created|updated|purchased|dt|_at)$', re.IGNORECASE)
PRICE_PATTERN = re.compile(r'(price|cost|amount|sale|revenue|spend|mrp|val|value)$', re.IGNORECASE)
RATING_PATTERN = re.compile(r'^(rating|score|stars|like|dislike|interaction|label|target)$', re.IGNORECASE)
QUANTITY_PATTERN = re.compile(r'^(qty|quantity|count|units|volume)$', re.IGNORECASE)


def classify_column(col_name: str, series: pd.Series, user_desc: str = "") -> Dict[str, Any]:
    """
    Classifies a single pandas Series into data type, entity type, and default cleansing rules.
    """
    n_total = len(series)
    n_null = int(series.isna().sum())
    n_unique = int(series.nunique(dropna=True))
    dtype_str = str(series.dtype)

    result = {
        "column_name": col_name,
        "dtype": dtype_str,
        "n_total": n_total,
        "n_null": n_null,
        "n_unique": n_unique,
        "user_description": user_desc,
        "column_type": "unknown",
        "entity_type": "context",
        "suggested_cleansing_rule": "none",
        "confidence": 1.0
    }

    # 1. Identifier Detection
    if ID_PATTERN.search(col_name):
        result["column_type"] = "identifier"
        if USER_ID_PATTERN.search(col_name):
            result["entity_type"] = "user"
        elif ITEM_ID_PATTERN.search(col_name):
            result["entity_type"] = "item"
        else:
            result["entity_type"] = "interaction"
        result["suggested_cleansing_rule"] = "none"
        return result

    # 2. Timestamp Detection
    if TIME_PATTERN.search(col_name) or pd.api.types.is_datetime64_any_dtype(series):
        result["column_type"] = "timestamp"
        result["entity_type"] = "interaction"
        result["suggested_cleansing_rule"] = "parse_datetime"
        return result

    # 3. Numeric Column Detection
    if pd.api.types.is_numeric_dtype(series):
        non_null_series = series.dropna()
        
        # Check target / rating
        if RATING_PATTERN.search(col_name):
            result["column_type"] = "target"
            result["entity_type"] = "interaction"
            result["suggested_cleansing_rule"] = "impute_mean" if n_null > 0 else "none"
            return result

        # Calculate Skewness & Outliers if sufficient data
        skew = float(non_null_series.skew()) if len(non_null_series) > 10 else 0.0
        
        # Outlier Detection (1.5 * IQR Rule)
        has_outliers = False
        outlier_count = 0
        if len(non_null_series) > 10:
            q1 = float(non_null_series.quantile(0.25))
            q3 = float(non_null_series.quantile(0.75))
            iqr = q3 - q1
            if iqr > 0:
                outlier_count = int(((non_null_series < q1 - 1.5 * iqr) | (non_null_series > q3 + 1.5 * iqr)).sum())
                has_outliers = outlier_count > 0

        result["has_outliers"] = has_outliers
        result["outlier_count"] = outlier_count
        
        if (PRICE_PATTERN.search(col_name) or QUANTITY_PATTERN.search(col_name) or abs(skew) > 0.75 or has_outliers) and n_unique > 5:
            result["column_type"] = "numerical_continuous"
            result["entity_type"] = "item" if PRICE_PATTERN.search(col_name) else "interaction"
            
            # Suggest transformations based on skewness and outliers
            if skew > 0.75:
                result["suggested_cleansing_rule"] = "log_transform"  # Right-skewed (tail on right)
            elif skew < -0.75:
                result["suggested_cleansing_rule"] = "square_transform"  # Left-skewed (tail on left)
            elif has_outliers:
                result["suggested_cleansing_rule"] = "cap_outliers_iqr"  # Heavy outliers with moderate skewness
            elif n_null > 0:
                result["suggested_cleansing_rule"] = "impute_median"
            else:
                result["suggested_cleansing_rule"] = "none"
        else:
            if n_unique <= 10:
                result["column_type"] = "categorical"
                result["suggested_cleansing_rule"] = "one_hot_encode" if n_unique <= 5 else "label_encode"
            else:
                result["column_type"] = "numerical_discrete"
                result["suggested_cleansing_rule"] = "impute_median" if n_null > 0 else "none"

        return result

    # 4. Categorical / Text Detection (String / Object / Categorical dtypes)
    if n_unique <= 50:
        result["column_type"] = "categorical"
        result["suggested_cleansing_rule"] = "one_hot_encode" if n_unique <= 5 else "frequency_encode"
        if n_null > 0:
            result["suggested_cleansing_rule"] = "impute_mode"
    else:
        result["column_type"] = "text"
        result["suggested_cleansing_rule"] = "none"

    return result


def classify_dataframe(df: pd.DataFrame, file_name: str, user_dict: Dict[str, str] = None) -> Dict[str, Any]:
    """
    Runs classification across all columns in a given DataFrame.
    """
    user_dict = user_dict or {}
    classified_cols = {}
    
    for col in df.columns:
        desc = user_dict.get(col, "")
        classified_cols[col] = classify_column(str(col), df[col], user_desc=desc)

    return {
        "file_name": file_name,
        "total_rows": len(df),
        "total_cols": len(df.columns),
        "columns": classified_cols
    }
