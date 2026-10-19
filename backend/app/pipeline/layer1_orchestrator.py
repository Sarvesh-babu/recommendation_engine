"""
Layer 1 Refinement: Master Pipeline Orchestrator.
Combines Deterministic Schema Classification, Enriched Data Dictionary,
Anti-Overlap LLM Prompting, Statistical Validation Engine, and Clean Baseline Rules.


"""

import pandas as pd
from typing import Dict, Any, List

from app.pipeline.schema_classifier import classify_dataframe
from app.pipeline.cleansing_wrappers import (
    impute_median, impute_mode, log_transform, square_transform,
    parse_datetime_features, aggregate_cross_file_baseline, safe_fillna
)
from app.pipeline.llm_prompt_builder import build_llm_prompt_payload
from app.pipeline.llm_service import call_realtime_llm
from app.pipeline.ast_validator import filter_safe_rules
from app.pipeline.rule_executor import HybridRuleExecutor
from app.pipeline.statistical_validator import run_statistical_validation


def run_baseline_refinement(
    dfs: Dict[str, pd.DataFrame],
    primary_file_name: str,
    user_data_dict: Dict[str, str] = None
) -> tuple[Dict[str, pd.DataFrame], Dict[str, Any], List[str]]:
    """
    Executes STAGE 1 & STAGE 2: Deterministic Schema Classification & Clean Baseline Transformations.
    Returns (baseline_dfs, classified_schema, applied_baseline_rules).
    """
    user_data_dict = user_data_dict or {}
    primary_df = dfs[primary_file_name]
    file_key_lower = primary_file_name.lower()

    # STAGE 1: DETERMINISTIC SCHEMA CLASSIFICATION
    classified_schema = classify_dataframe(primary_df, primary_file_name, user_dict=user_data_dict)

    # STAGE 2: DETERMINISTIC BASELINE EXECUTION
    dfs_copy = {k: v.copy() for k, v in dfs.items()}
    baseline_df = dfs_copy[primary_file_name]
    applied_baseline_rules = []

    for col_name, meta in classified_schema.get("columns", {}).items():
        rule_name = meta.get("suggested_cleansing_rule")

        if rule_name == "log_transform":
            baseline_df = log_transform(baseline_df, col_name)
            applied_baseline_rules.append(f"Log Skewness Reduction on '{col_name}' -> created '{col_name}_log'")
        elif rule_name == "square_transform":
            baseline_df = square_transform(baseline_df, col_name)
            applied_baseline_rules.append(f"Square Skewness Reduction on '{col_name}' -> created '{col_name}_squared'")
        elif rule_name == "parse_datetime":
            baseline_df = parse_datetime_features(baseline_df, col_name)
            applied_baseline_rules.append(f"Extracted Date Features (Year, Month, Day, Weekend) from '{col_name}'")
        elif rule_name == "impute_median":
            baseline_df = impute_median(baseline_df, col_name)
            applied_baseline_rules.append(f"Filled Missing Values (Median) in '{col_name}'")
        elif rule_name == "impute_mode":
            baseline_df = impute_mode(baseline_df, col_name)
            applied_baseline_rules.append(f"Filled Missing Values (Mode) in '{col_name}'")

    dfs_copy[primary_file_name] = baseline_df

    # Clean cross-file aggregations
    if len(dfs_copy) > 1:
        dfs_copy = aggregate_cross_file_baseline(dfs_copy)
        if "cust" in file_key_lower or "user" in file_key_lower:
            applied_baseline_rules.extend([
                "Total Customer Spend (Joined from Transactions)",
                "Customer Order Count (Joined from Transactions)",
                "Customer Average Order Value (Joined from Transactions)"
            ])
        elif "prod" in file_key_lower or "item" in file_key_lower or "sku" in file_key_lower:
            applied_baseline_rules.extend([
                "Total Product Volume Sold (Joined from Transactions)",
                "Total Product Revenue (Joined from Transactions)"
            ])

    return dfs_copy, classified_schema, applied_baseline_rules


def run_layer1_refinement(
    dfs: Dict[str, pd.DataFrame],
    user_data_dict: Dict[str, str] = None,
    api_key: str = None
) -> Dict[str, Any]:
    """
    Executes complete Layer 1 Refinement Workflow with Clean Baseline Rules & Statistical Validator.
    """
    user_data_dict = user_data_dict or {}
    primary_file_name = list(dfs.keys())[0]
    primary_df = dfs[primary_file_name]

    baseline_dfs, classified_schema, applied_baseline_rules = run_baseline_refinement(
        dfs=dfs,
        primary_file_name=primary_file_name,
        user_data_dict=user_data_dict
    )
    baseline_df = baseline_dfs[primary_file_name]

    # Re-classify baseline_df
    updated_schema = classify_dataframe(baseline_df, primary_file_name, user_dict=user_data_dict)
    existing_columns = list(baseline_df.columns)

    # STAGE 3: ANTI-OVERLAP LLM PROMPT GENERATION & API CALL
    llm_payload = build_llm_prompt_payload(
        classified_schema=updated_schema,
        user_data_dict=user_data_dict,
        applied_baseline_rules=applied_baseline_rules,
        existing_columns=existing_columns
    )

    llm_response = call_realtime_llm(llm_payload, api_key=api_key)

    raw_cleansing = llm_response.get("recommended_cleansing_rules", [])
    raw_features = llm_response.get("recommended_feature_engineering", [])

    filtered_features = [
        rule for rule in raw_features
        if rule.get("feature_name", "").lower() not in set(c.lower() for c in existing_columns)
    ]

    # STAGE 4: AST SECURITY AUDIT
    approved_cleansing, rejected_cleansing = filter_safe_rules(raw_cleansing)
    approved_features, rejected_features = filter_safe_rules(filtered_features)

    # STAGE 5: HYBRID EXECUTION ON APPROVED RULES
    executor = HybridRuleExecutor()
    dfs_to_execute = {primary_file_name: baseline_df}
    all_selected_rules = approved_cleansing + approved_features

    refined_dfs, exec_log = executor.execute_pipeline(dfs_to_execute, all_selected_rules)
    refined_df = refined_dfs[primary_file_name]

    # STAGE 6: STATISTICAL VALIDATION ENGINE
    stat_val_results = run_statistical_validation(
        df=refined_df,
        original_df=primary_df
    )

    # Re-classify refined_df to categorize all final features
    final_schema = classify_dataframe(refined_df, primary_file_name, user_dict=user_data_dict)

    return {
        "status": "success",
        "primary_file_name": primary_file_name,
        "enriched_data_dictionary": final_schema,
        "applied_baseline_rules": applied_baseline_rules,
        "llm_recommendations": {
            "cleansing_rules": approved_cleansing,
            "feature_engineering_rules": approved_features
        },
        "statistical_validation": stat_val_results,
        "security_audit": {
            "approved_rules_count": len(approved_cleansing) + len(approved_features),
            "blocked_rules_count": len(rejected_cleansing) + len(rejected_features),
            "blocked_details": rejected_cleansing + rejected_features
        },
        "execution_log": exec_log,
        "refined_shape": {"rows": len(refined_df), "cols": len(refined_df.columns)},
        "original_columns": list(primary_df.columns),
        "engineered_columns": [c for c in refined_df.columns if c not in primary_df.columns],
        "preview_data": safe_fillna(refined_df.head(50), "").to_dict(orient="records")
    }
