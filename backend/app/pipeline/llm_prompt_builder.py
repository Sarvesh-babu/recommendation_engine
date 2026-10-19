"""
Layer 1 Refinement: System Prompt Builder with Enriched Data Dictionary & Anti-Overlap Guard.

"""

import json
import pandas as pd
from typing import Dict, Any, List
from .rule_catalog import list_catalog_for_prompt


SYSTEM_PROMPT = """You are the Principal Data Intelligence Agent for an Enterprise Retail Recommendation Engine.
Analyze metadata profiles and Enriched Data Dictionaries from uploaded CSV files and generate advanced, non-overlapping feature engineering proposals.

PHASE 1: ENRICHED DATA DICTIONARY & SCHEMA RECOGNITION
1. Read the provided Enriched Data Dictionary containing user descriptions, column dtypes, unique counts, skewness, and auto-classified entity roles (user, item, interaction, context).
2. Respect existing baseline transformations already executed deterministically by the system.

PHASE 2: ANTI-OVERLAP & DEDUPLICATION CONSTRAINTS (CRITICAL)
1. DO NOT suggest any column transformations or features listed in 'already_applied_baseline_rules'.
2. DO NOT suggest any features that output a column name already present in 'existing_column_names'.
3. Focus ONLY on dynamic, high-value, domain-specific features (e.g., RFM scores, purchase recency, user category affinity, interaction frequency) that complement the baseline.

PHASE 3: FEATURE ENGINEERING CONTRACT & TAXONOMY
1. SAFE MATH CONTRACT: All division expressions MUST handle division-by-zero using `.replace(0, np.nan)` and end with `.fillna(0)`.
2. ONE-LINE VECTORIZED CODE: Every rule's code_snippet MUST be a valid 1-line vectorized Pandas/NumPy expression assigning to `df['feature_name']`.
3. EXPLICIT RULE CATALOG MATCHING: Where applicable, map your suggested feature to a known Rule ID from the provided 'available_rule_catalog'.

OUTPUT FORMAT CONTRACT:
Respond ONLY with a valid JSON object matching this schema:
{
  "enriched_data_dictionary_summary": {
    "file_name": "string",
    "key_insights": "string under 15 words"
  },
  "recommended_cleansing_rules": [
    {
      "rule_id": "RULE_ID_FROM_CATALOG_OR_CUSTOM",
      "target_column": "raw_col_name",
      "transformation_name": "clean_rule_name",
      "rationale": "short explanation under 10 words",
      "code_snippet": "pandas snippet"
    }
  ],
  "recommended_feature_engineering": [
    {
      "rule_id": "RULE_ID_FROM_CATALOG_OR_CUSTOM",
      "feature_name": "new_feature_column_name",
      "feature_type": "RFM|Affinity|Tenure|Velocity|Ratio|Encoding|Interaction",
      "rationale": "short explanation under 10 words",
      "code_snippet": "pandas snippet"
    }
  ]
}
"""


def format_enriched_data_dictionary(classified_schema: Dict[str, Any], user_dict: Dict[str, str] = None) -> Dict[str, Any]:
    """
    Combines deterministic classification output with user-provided descriptions into an Enriched Data Dictionary payload.
    """
    user_dict = user_dict or {}
    columns_info = classified_schema.get("columns", {})
    
    enriched_dict = {
        "file_name": classified_schema.get("file_name", "unknown.csv"),
        "total_rows": classified_schema.get("total_rows", 0),
        "columns": {}
    }

    for col, meta in columns_info.items():
        enriched_dict["columns"][col] = {
            "user_description": user_dict.get(col, meta.get("user_description", "")),
            "dtype": meta.get("dtype", "unknown"),
            "column_type": meta.get("column_type", "unknown"),
            "entity_type": meta.get("entity_type", "context"),
            "null_count": meta.get("n_null", 0),
            "unique_count": meta.get("n_unique", 0),
            "suggested_baseline_rule": meta.get("suggested_cleansing_rule", "none")
        }

    return enriched_dict


def build_llm_prompt_payload(
    classified_schema: Dict[str, Any],
    user_data_dict: Dict[str, str] = None,
    applied_baseline_rules: List[str] = None,
    existing_columns: List[str] = None
) -> Dict[str, Any]:
    """
    Constructs the complete payload containing Enriched Data Dictionary, Applied Baseline Rules,
    Rule Catalog, and System Prompt for the LLM.
    """
    enriched_dict = format_enriched_data_dictionary(classified_schema, user_data_dict)
    applied_rules = applied_baseline_rules or []
    existing_cols = existing_columns or list(enriched_dict["columns"].keys())
    catalog_summary = list_catalog_for_prompt()

    user_prompt_content = {
        "ENRICHED_DATA_DICTIONARY": enriched_dict,
        "ALREADY_APPLIED_BASELINE_RULES": applied_rules,
        "EXISTING_COLUMN_NAMES": existing_cols,
        "AVAILABLE_RULE_CATALOG": catalog_summary
    }

    return {
        "system_prompt": SYSTEM_PROMPT,
        "user_prompt": f"INPUT DATA DICTIONARY & CONTEXT:\n{json.dumps(user_prompt_content, indent=2)}",
        "enriched_data_dictionary": enriched_dict
    }
