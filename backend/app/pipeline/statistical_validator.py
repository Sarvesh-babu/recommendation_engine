"""
Statistical Validator Layer for Retail Recommendation Engine (User-Protected Edition).

Focuses strictly on raw dataset quality defects:
1. Row Count Integrity Check (ensures joins/transforms haven't duplicated or dropped rows).
2. Zero / Near-Zero Variance Detection on ORIGINAL dataset columns (std == 0).
3. Extreme Outlier Detection on numeric values (Q3 + 3.0 * IQR).
4. Target Leakage Detection (|r_target| > 0.98).

Protects user-ticked AI features from zero-variance deletion proposals.

File: backend/app/pipeline/statistical_validator.py
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List


def run_statistical_validation(
    df: pd.DataFrame,
    original_df: pd.DataFrame = None,
    target_col: str = None
) -> Dict[str, Any]:
    """
    Runs statistical audit on DataFrame and generates clean, non-conflicting action proposals.
    """
    actions = []
    warnings = []
    
    # 1. ROW COUNT INTEGRITY CHECK
    original_rows = len(original_df) if original_df is not None else len(df)
    current_rows = len(df)
    row_count_matched = (original_rows == current_rows)
    
    if not row_count_matched:
        warnings.append(
            f"Row Count Mismatch Detected: Original rows ({original_rows}) vs Refined rows ({current_rows})."
        )

    original_cols_set = set(original_df.columns) if original_df is not None else set(df.columns)
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]

    # 2. ZERO & NEAR-ZERO VARIANCE CHECK (ONLY ON ORIGINAL/BASELINE COLUMNS)
    for col in df.columns:
        # Only suggest dropping zero-variance if it's an ORIGINAL column (e.g. constant timestamp_year)
        if col in original_cols_set:
            n_unique = df[col].nunique(dropna=True)
            if n_unique <= 1:
                actions.append({
                    "action_id": f"stat_zero_var_{col}",
                    "action_type": "drop_column",
                    "target_column": col,
                    "reason": f"Zero Variance (std = 0, {n_unique} unique value) — Contains no predictive information.",
                    "severity": "high",
                    "code_snippet": f"df = df.drop(columns=['{col}'])"
                })
            elif n_unique > 1 and len(df) > 20:
                top_freq = df[col].value_counts(normalize=True, dropna=False).iloc[0]
                if top_freq >= 0.99:
                    actions.append({
                        "action_id": f"stat_quasi_const_{col}",
                        "action_type": "drop_column",
                        "target_column": col,
                        "reason": f"Quasi-Constant Feature ({top_freq*100:.1f}% rows share single value) — High sparsity/noise.",
                        "severity": "medium",
                        "code_snippet": f"df = df.drop(columns=['{col}'])"
                    })

    # 3. EXTREME OUTLIERS CHECK (NUMERIC)
    for col in numeric_cols:
        series = df[col].dropna()
        if len(series) > 20:
            q1 = series.quantile(0.25)
            q3 = series.quantile(0.75)
            iqr = q3 - q1
            if iqr > 0:
                lower_bound = q1 - 3.0 * iqr
                upper_bound = q3 + 3.0 * iqr
                outlier_count = int(((series < lower_bound) | (series > upper_bound)).sum())
                
                if outlier_count > 0:
                    actions.append({
                        "action_id": f"stat_outlier_{col}",
                        "action_type": "cap_outliers",
                        "target_column": col,
                        "reason": f"Heavy Outliers Detected ({outlier_count} rows > 3.0*IQR bounds) — Recommend capping bounds.",
                        "severity": "low",
                        "code_snippet": f"q1 = df['{col}'].quantile(0.25)\nq3 = df['{col}'].quantile(0.75)\niqr = q3 - q1\ndf['{col}'] = df['{col}'].clip(lower=q1 - 1.5*iqr, upper=q3 + 1.5*iqr)"
                    })

    # 4. TARGET LEAKAGE CHECK
    if target_col and target_col in numeric_cols:
        for col in numeric_cols:
            if col != target_col:
                r_target = abs(df[col].corr(df[target_col]))
                if r_target >= 0.98:
                    actions.append({
                        "action_id": f"stat_leakage_{col}",
                        "action_type": "drop_column",
                        "target_column": col,
                        "reason": f"Potential Target Leakage (r = {r_target:.2f} with target '{target_col}') — Cheating feature.",
                        "severity": "high",
                        "code_snippet": f"df = df.drop(columns=['{col}'])"
                    })

    return {
        "status": "success" if not warnings else "warning",
        "row_integrity": {
            "original_rows": original_rows,
            "refined_rows": current_rows,
            "matched": row_count_matched
        },
        "warnings": warnings,
        "action_proposals": actions
    }
