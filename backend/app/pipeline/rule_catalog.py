"""
Static Rule Catalog for Data Cleansing, Transformation & Feature Engineering.

Defines the registry of all standard rule IDs, metadata, and maps them to their
corresponding deterministic wrapper functions in cleansing_wrappers.py.
"""

from typing import Dict, Any, List
from . import cleansing_wrappers


# Rule Catalog Data Structure
RULE_CATALOG: Dict[str, Dict[str, Any]] = {
    # ---------------------------------------------------------
    # 1. IMPUTATION RULES (NULL HANDLING)
    # ---------------------------------------------------------
    "RULE_IMP_MEDIAN": {
        "rule_id": "RULE_IMP_MEDIAN",
        "display_name": "Median Imputation",
        "category": "cleansing",
        "description": "Fills missing values in a numeric column with the column median.",
        "func": cleansing_wrappers.impute_median,
        "required_params": ["col"]
    },
    "RULE_IMP_MEAN": {
        "rule_id": "RULE_IMP_MEAN",
        "display_name": "Mean Imputation",
        "category": "cleansing",
        "description": "Fills missing values in a numeric column with the column mean.",
        "func": cleansing_wrappers.impute_mean,
        "required_params": ["col"]
    },
    "RULE_IMP_MODE": {
        "rule_id": "RULE_IMP_MODE",
        "display_name": "Mode Imputation",
        "category": "cleansing",
        "description": "Fills missing values in a categorical column with the most frequent value (mode).",
        "func": cleansing_wrappers.impute_mode,
        "required_params": ["col"]
    },
    "RULE_IMP_CONSTANT": {
        "rule_id": "RULE_IMP_CONSTANT",
        "display_name": "Constant Imputation",
        "category": "cleansing",
        "description": "Fills missing values with a specified constant value.",
        "func": cleansing_wrappers.impute_constant,
        "required_params": ["col", "fill_value"]
    },

    # ---------------------------------------------------------
    # 2. TRANSFORMATION RULES (SKEWNESS & OUTLIERS)
    # ---------------------------------------------------------
    "RULE_TRF_LOG": {
        "rule_id": "RULE_TRF_LOG",
        "display_name": "Log1p Transformation",
        "category": "transformation",
        "description": "Applies log(x+1) transformation to handle right-skewed numeric data.",
        "func": cleansing_wrappers.log_transform,
        "required_params": ["col"]
    },
    "RULE_TRF_SQUARE": {
        "rule_id": "RULE_TRF_SQUARE",
        "display_name": "Square Transformation",
        "category": "transformation",
        "description": "Applies square transformation (x^2) to handle left-skewed numeric data (e.g., ratings).",
        "func": cleansing_wrappers.square_transform,
        "required_params": ["col"]
    },
    "RULE_TRF_CAP_OUTLIERS": {
        "rule_id": "RULE_TRF_CAP_OUTLIERS",
        "display_name": "IQR Outlier Capping",
        "category": "transformation",
        "description": "Caps extreme numeric values outside 1.5 * IQR bounds.",
        "func": cleansing_wrappers.cap_outliers_iqr,
        "required_params": ["col"]
    },
    "RULE_TRF_CAP_ZSCORE": {
        "rule_id": "RULE_TRF_CAP_ZSCORE",
        "display_name": "Z-Score Outlier Capping (3-Sigma)",
        "category": "transformation",
        "description": "Caps extreme numeric values beyond 3 standard deviations from the mean (mean +/- 3*std).",
        "func": cleansing_wrappers.cap_outliers_zscore,
        "required_params": ["col"]
    },
    "RULE_TRF_CAP_PERCENTILE": {
        "rule_id": "RULE_TRF_CAP_PERCENTILE",
        "display_name": "Percentile Winsorization (1st-99th)",
        "category": "transformation",
        "description": "Winsorizes numeric outliers by capping values below the 1st percentile and above the 99th percentile.",
        "func": cleansing_wrappers.cap_outliers_percentile,
        "required_params": ["col"]
    },

    # ---------------------------------------------------------
    # 3. ENCODING RULES
    # ---------------------------------------------------------
    "RULE_ENC_ONEHOT": {
        "rule_id": "RULE_ENC_ONEHOT",
        "display_name": "One-Hot Encoding",
        "category": "encoding",
        "description": "Converts categorical strings into binary indicator columns.",
        "func": cleansing_wrappers.one_hot_encode,
        "required_params": ["col"]
    },
    "RULE_ENC_LABEL": {
        "rule_id": "RULE_ENC_LABEL",
        "display_name": "Label Encoding",
        "category": "encoding",
        "description": "Encodes categorical strings into integer codes.",
        "func": cleansing_wrappers.label_encode,
        "required_params": ["col"]
    },
    "RULE_ENC_FREQ": {
        "rule_id": "RULE_ENC_FREQ",
        "display_name": "Frequency Encoding",
        "category": "encoding",
        "description": "Replaces categorical values with their percentage frequency in the dataset.",
        "func": cleansing_wrappers.frequency_encode,
        "required_params": ["col"]
    },

    # ---------------------------------------------------------
    # 4. DATETIME PARSING RULES
    # ---------------------------------------------------------
    "RULE_TIME_PARSE": {
        "rule_id": "RULE_TIME_PARSE",
        "display_name": "Parse Datetime Features",
        "category": "datetime",
        "description": "Extracts year, month, day, dayofweek, and weekend flags from timestamp columns.",
        "func": cleansing_wrappers.parse_datetime_features,
        "required_params": ["col"]
    },

    # ---------------------------------------------------------
    # 5. SINGLE-FILE FEATURE ENGINEERING RULES
    # ---------------------------------------------------------
    "RULE_FEAT_TOTAL_AMOUNT": {
        "rule_id": "RULE_FEAT_TOTAL_AMOUNT",
        "display_name": "Compute Total Amount",
        "category": "feature_engineering",
        "description": "Computes total_amount = price * quantity in transaction tables.",
        "func": cleansing_wrappers.compute_total_amount,
        "required_params": ["price_col", "qty_col"]
    },
    "RULE_FEAT_AGE_BIN": {
        "rule_id": "RULE_FEAT_AGE_BIN",
        "display_name": "Bin Customer Age",
        "category": "feature_engineering",
        "description": "Bins customer age into brackets (<18, 18-24, 25-34, 35-49, 50+).",
        "func": cleansing_wrappers.bin_customer_age,
        "required_params": ["col"]
    },
    "RULE_FEAT_PRICE_TIER": {
        "rule_id": "RULE_FEAT_PRICE_TIER",
        "display_name": "Bin Price Tiers",
        "category": "feature_engineering",
        "description": "Bins product price into quantile tiers (budget, mid_tier, premium).",
        "func": cleansing_wrappers.bin_price_tiers,
        "required_params": ["col"]
    },
    "RULE_FEAT_DISCOUNT_PCT": {
        "rule_id": "RULE_FEAT_DISCOUNT_PCT",
        "display_name": "Compute Discount Percentage",
        "category": "feature_engineering",
        "description": "Computes discount percentage from original MRP and sale price.",
        "func": cleansing_wrappers.compute_discount_percentage,
        "required_params": ["mrp_col", "sale_col"]
    },
    "RULE_FEAT_TENURE": {
        "rule_id": "RULE_FEAT_TENURE",
        "display_name": "Compute Account Tenure",
        "category": "feature_engineering",
        "description": "Computes account age in days from customer signup date.",
        "func": cleansing_wrappers.compute_account_tenure,
        "required_params": ["signup_date_col"]
    },

    # ---------------------------------------------------------
    # 6. CROSS-FILE AGGREGATION RULES
    # ---------------------------------------------------------
    "RULE_CROSS_BASELINE": {
        "rule_id": "RULE_CROSS_BASELINE",
        "display_name": "Cross-File Aggregations",
        "category": "cross_file",
        "description": "Aggregates spend, order count, and product sales across multiple CSV tables.",
        "func": cleansing_wrappers.aggregate_cross_file_baseline,
        "required_params": []
    }
}


def get_rule_by_id(rule_id: str) -> Dict[str, Any]:
    """Retrieves a rule entry from the catalog by ID."""
    return RULE_CATALOG.get(rule_id, None)


def list_catalog_for_prompt() -> List[Dict[str, str]]:
    """Returns a simplified list of rules formatted for inclusion in LLM prompts."""
    return [
        {
            "rule_id": key,
            "display_name": val["display_name"],
            "category": val["category"],
            "description": val["description"]
        }
        for key, val in RULE_CATALOG.items()
    ]
