"""
Hybrid Rule Executor Engine for Retail Recommendation Accelerator.
Executes both static catalog cleansing rules and AST-validated custom pandas code snippets.


"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List, Tuple
from app.pipeline.rule_catalog import RULE_CATALOG
from app.pipeline.ast_validator import is_code_safe
from app.pipeline import cleansing_wrappers


class HybridRuleExecutor:
    def __init__(self):
        self.catalog = RULE_CATALOG

    def execute_rule(self, df: pd.DataFrame, rule: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """Executes a single rule against a DataFrame."""
        rule_id = rule.get("rule_id", "CUSTOM")
        action_type = rule.get("action_type")
        target_col = rule.get("target_column")
        code_snippet = rule.get("code_snippet")

        log_entry = {
            "rule_id": rule_id,
            "status": "success",
            "message": "",
            "cols_added": []
        }

        cols_before = set(df.columns)

        try:
            # Action Type: Drop Column
            if action_type == "drop_column" and target_col in df.columns:
                df = df.drop(columns=[target_col])
                log_entry["message"] = f"Dropped column '{target_col}'"
                return df, log_entry

            # Action Type: Cap Outliers (IQR / Z-Score / Percentile)
            if action_type in ["cap_outliers", "cap_outliers_iqr"] and target_col in df.columns and pd.api.types.is_numeric_dtype(df[target_col]):
                df = cleansing_wrappers.cap_outliers_iqr(df, target_col)
                log_entry["message"] = f"Capped outliers (IQR) in '{target_col}'"
                return df, log_entry

            if action_type == "cap_outliers_zscore" and target_col in df.columns and pd.api.types.is_numeric_dtype(df[target_col]):
                df = cleansing_wrappers.cap_outliers_zscore(df, target_col)
                log_entry["message"] = f"Capped outliers (Z-score 3-sigma) in '{target_col}'"
                return df, log_entry

            if action_type == "cap_outliers_percentile" and target_col in df.columns and pd.api.types.is_numeric_dtype(df[target_col]):
                df = cleansing_wrappers.cap_outliers_percentile(df, target_col)
                log_entry["message"] = f"Winsorized outliers (1st-99th percentile) in '{target_col}'"
                return df, log_entry

            # Catalog Rule Execution
            if rule_id in self.catalog:
                func = self.catalog[rule_id]["func"]
                col_name = rule.get("target_column")
                df = func(df, col_name) if col_name else func(df)
                log_entry["message"] = f"Executed catalog rule '{rule_id}'"
            # AST Code Snippet Execution
            elif code_snippet:
                if not is_code_safe(code_snippet):
                    log_entry["status"] = "blocked"
                    log_entry["message"] = f"Code snippet failed AST security audit: '{code_snippet}'"
                    return df, log_entry

                local_vars = {"df": df, "np": np, "pd": pd}
                exec(code_snippet, {"__builtins__": None}, local_vars)
                df = local_vars["df"]
                log_entry["message"] = f"Executed safe python snippet for '{rule_id}'"
            else:
                log_entry["status"] = "skipped"
                log_entry["message"] = f"No executable logic found for rule '{rule_id}'"

            cols_after = set(df.columns)
            log_entry["cols_added"] = list(cols_after - cols_before)

        except Exception as e:
            log_entry["status"] = "error"
            log_entry["message"] = f"Execution error on rule '{rule_id}': {str(e)}"

        return df, log_entry

    def execute_pipeline(
        self,
        dfs: Dict[str, pd.DataFrame],
        rules: List[Dict[str, Any]],
        target_dataset_name: str = None
    ) -> Tuple[Dict[str, pd.DataFrame], Dict[str, Any]]:
        """Executes a list of rules across target DataFrames."""
        execution_logs = []
        if target_dataset_name and target_dataset_name.lower() in dfs:
            primary_key = target_dataset_name.lower()
        elif "transactions" in dfs:
            primary_key = "transactions"
        else:
            primary_key = list(dfs.keys())[0]

        for rule in rules:
            target_df_key = rule.get("target_dataset", primary_key).lower()
            if target_df_key in dfs:
                dfs[target_df_key], log = self.execute_rule(dfs[target_df_key], rule)
                execution_logs.append(log)
            else:
                # Fallback: check if target_col exists in any df
                target_col = rule.get("target_column")
                found_key = None
                if target_col:
                    for k, df in dfs.items():
                        if target_col in df.columns:
                            found_key = k
                            break
                df_key_to_use = found_key or primary_key
                dfs[df_key_to_use], log = self.execute_rule(dfs[df_key_to_use], rule)
                execution_logs.append(log)

        all_added_cols = []
        for log in execution_logs:
            all_added_cols.extend(log.get("cols_added", []))

        summary = {
            "total_rules_evaluated": len(rules),
            "successful_rules": sum(1 for l in execution_logs if l["status"] == "success"),
            "blocked_rules": sum(1 for l in execution_logs if l["status"] == "blocked"),
            "failed_rules": sum(1 for l in execution_logs if l["status"] == "error"),
            "engineered_columns": list(set(all_added_cols)),
            "logs": execution_logs
        }

        return dfs, summary

