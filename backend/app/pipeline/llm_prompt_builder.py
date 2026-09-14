"""
Layer 1 Refinement: Universal Multi-Industry System Prompt Builder
File: backend/app/pipeline/llm_prompt_builder.py
"""

import json
import pandas as pd
from typing import Dict, Any


SYSTEM_PROMPT = """You are the Principal Universal Data Intelligence Agent for an Enterprise Recommendation Engine.
Analyze metadata profiles from ANY of the 6 universal file types across ALL industries (Retail, Streaming/Media, Insurance/Finance, Healthcare, E-Learning, SaaS) and generate data cleansing and feature engineering transformation rules.

PHASE 1: UNIVERSAL SCHEMA CLASSIFICATION
Classify EVERY incoming column into exactly ONE canonical role:
- actor_id: Primary entity performing actions (customer_id, subscriber_id, policyholder_id, patient_id, user_id). High cardinality.
- object_id: Primary entity being acted upon (product_id, content_id, movie_id, plan_id, course_id, stock_code). High cardinality.
- interaction_value: Continuous numeric measure of interaction intensity (spend, watch_duration_sec, completion_pct, premium_amt, quantity, rating). Continuous numeric, NOT binary.
- timestamp: Actual parseable date/time column (transaction_date, stream_time, invoice_date, watch_date, claim_date). Days-since counters (Vintage, order_number) MUST be classified as context_attribute.
- context_attribute: ALL other columns (demographics, binary 0/1 flags, categories, region codes, device types, channel IDs, tier tags).
- target_variable: Known prediction label/response (Response, is_purchased, is_churned, is_renewed).

STRICT CLASSIFICATION RULES:
1. Binary 0/1 flags -> ALWAYS context_attribute.
2. Low-cardinality categoricals -> ALWAYS context_attribute.
3. SYMMETRIC ENTITY FALLBACK:
   - First identify actor_id from user/customer/subscriber ID columns. IF no explicit object_id exists, classify the highest-cardinality REMAINING context column as proxy object_id.
   - IF object_id is found but actor_id is missing, classify session_id / invoice_no / device_id or highest-cardinality remaining context column as proxy actor_id.

PHASE 2: DATA CLEANSING & FEATURE ENGINEERING TAXONOMY

PART A: UNIVERSAL DATA CLEANSING RULES
1. Null Imputation: Median for skewed numerics, mean for symmetric numerics, "__unknown__" for categoricals.
2. Quantile Winsorization: Two-sided quantile clipping (q01 to q99) for continuous skewed attributes: `lower = df[col].quantile(0.01); upper = df[col].quantile(0.99); df[col] = df[col].clip(lower=lower, upper=upper)`.
3. Right-Skewness Transformation: Apply np.log1p() to heavy right-skewed positive continuous metrics (prices, spend, duration, volume).
4. Left-Skewness Transformation: Apply np.square() or np.power(df[col], 2) to heavy left-skewed continuous metrics (completion rates, ratings, satisfaction scores).
5. Selective Non-Negative Clipping: Apply lower-clip(0) ONLY to naturally non-negative attributes (Age, Tenure, Duration) when negative values represent logging corruption. Do NOT clip if negative values represent returns/refunds/claims/loss.
6. Rare Category Collapsing: Collapse categories with <1% frequency into "__other__": `freq = df[col].map(df[col].value_counts(normalize=True)); df[col] = df[col].where(freq >= 0.01, '__other__')`.

PART B: ADVANCED DOMAIN FEATURE ENGINEERING CATEGORIES
Generate high-impact feature_engineering_rules covering applicable feature families:
1. SCHEMA RELEVANCE: ONLY generate features for which source columns actually exist in the metadata profile. If no date/promo/price column exists, DO NOT generate urgency or promo features.
2. SAFE MATH CONTRACT: All ratio and divergence features MUST handle division-by-zero using `.replace(0, np.nan)` or `+ 1e-5` (e.g., `df['a'] / (df['b'].replace(0, np.nan))`).
3. ONE-LINE VECTORIZED CODE: Every code_snippet MUST be a valid 1-line vectorized Pandas/NumPy expression assigning to a new column `df['feature_name'] = ...`.

FEATURE TAXONOMY:
- Interaction & Event Files: Recency (`days_since_last_event`), Frequency (`event_count_per_actor`), Intensity (`total_interaction_value`).
- Actor Profile Files: Account tenure `(timestamp - signup_date)`, demographic binnings, segment frequency.
- Object Catalog Files: Category/Genre frequency, item popularity share, price/tier percentile in category.
- Offer & Campaign Files: Stacked discount/benefit depth `1 - ((1-d1)*(1-d2))`, offer urgency countdown `(offer_end - timestamp) / total_duration`, actor offer elasticity.
- Reversal & Claim Files: Actor claim/return risk ratio `reversal_events / total_events`, object defect/skip rate.
- Activity & Session Files: Session engagement ratio `duration / item_avg_duration`, search query intent, click conversion.

CRITICAL JSON OUTPUT CONTRACT:
Respond ONLY with a valid JSON object matching this schema. Keep rationale concise:
{
  "column_mappings": {
    "raw_col": {"role": "actor_id|object_id|interaction_value|timestamp|context_attribute|target_variable", "rationale": "short explanation"}
  },
  "data_cleansing_rules": [
    {"anomaly_type": "Nulls|Outlier|InvalidValue|Transformation", "transformation_name": "clean_rule_name", "rationale": "short explanation", "code_snippet": "pandas snippet"}
  ],
  "feature_engineering_rules": [
    {"feature_type": "Velocity|Divergence|Density|Encoding|Aggregation|Offer|Elasticity|Urgency|RFM|Tenure|Reversal|Session", "feature_name": "feature_col_name", "rationale": "short explanation", "code_snippet": "pandas snippet"}
  ]
}

CONSTRAINTS:
1. Use ONLY vectorizable pandas (df) and numpy (np) code strings.
2. NO row-by-row loops (iterrows).
3. Keep all 'rationale' text strictly under 10 words.
"""


def extract_metadata_profile(df: pd.DataFrame, file_type_label: str = None, sample_size: int = 1000) -> Dict[str, Any]:
    """
    Extracts 100% exact full-dataset statistics combined with top 1,000 text sample values.
    """
    sample_df = df.head(sample_size)
    profile = {
        "file_type_hint": file_type_label or "unknown",
        "shape": {"rows": len(df), "cols": len(df.columns)},
        "columns": {}
    }
    
    for col in df.columns:
        full_series = df[col]
        sample_series = sample_df[col]
        
        col_info = {
            "dtype": str(full_series.dtype),
            "null_pct": round(float(full_series.isnull().mean() * 100), 1),
            "nunique": int(full_series.nunique()),
            "sample_values": [str(v) for v in sample_series.dropna().head(3).tolist()]
        }
        if pd.api.types.is_numeric_dtype(full_series):
            col_info["mean"] = round(float(full_series.mean()), 2) if not full_series.isnull().all() else None
            col_info["min"] = round(float(full_series.min()), 2) if not full_series.isnull().all() else None
            col_info["max"] = round(float(full_series.max()), 2) if not full_series.isnull().all() else None
            col_info["q01"] = round(float(full_series.quantile(0.01)), 2) if not full_series.isnull().all() else None
            col_info["q99"] = round(float(full_series.quantile(0.99)), 2) if not full_series.isnull().all() else None
            skew_val = float(full_series.skew()) if len(full_series.dropna()) > 3 else 0.0
            col_info["skewness"] = round(skew_val, 2)
            col_info["skew_type"] = "right_skewed" if skew_val > 1.0 else ("left_skewed" if skew_val < -1.0 else "symmetric")
            
        profile["columns"][col] = col_info
        
    return profile


def build_llm_prompt_payload(df: pd.DataFrame, file_type_label: str = None) -> Dict[str, Any]:
    """
    Combines metadata profile and system prompt into ready-to-send API payload.
    """
    profile = extract_metadata_profile(df, file_type_label=file_type_label)
    return {
        "system_prompt": SYSTEM_PROMPT,
        "user_prompt": f"INPUT DATA METADATA PROFILE ({file_type_label or 'Generic'} File):\n{json.dumps(profile, indent=2)}",
        "profile": profile
    }
