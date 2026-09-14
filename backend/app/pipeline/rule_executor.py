"""
Layer 1 Refinement: Sandboxed Dynamic Execution Engine

"""

import pandas as pd
import numpy as np
from typing import List, Dict, Any, Tuple


class LLMRuleExecutor:
    """
    Sandboxed Dynamic Execution Engine for Layer 1 Data Cleansing & Feature Engineering.
    """
    
    def __init__(self):
        self.safe_builtins = {
            "len": len, "range": range, "max": max, "min": min,
            "abs": abs, "round": round, "str": str, "int": int, "float": float
        }
        self.exec_globals = {
            "np": np, "pd": pd, "__builtins__": self.safe_builtins
        }

    def execute_rule_pipeline(
        self, 
        df: pd.DataFrame, 
        cleansing_rules: List[Dict[str, Any]], 
        feature_rules: List[Dict[str, Any]]
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        refined_df = df.copy()
        local_scope = {"df": refined_df}
        
        execution_log = {
            "cleansing_executed": 0, "cleansing_failed": 0,
            "features_executed": 0, "features_failed": 0, "errors": []
        }

        # STAGE A: CLEANSING RULES
        for i, rule in enumerate(cleansing_rules, start=1):
            rule_name = rule.get("transformation_name", f"cleansing_rule_{i}")
            code_str = rule.get("code_snippet")
            if not code_str: continue
            try:
                exec(code_str, self.exec_globals, local_scope)
                execution_log["cleansing_executed"] += 1
            except Exception as e:
                execution_log["cleansing_failed"] += 1
                execution_log["errors"].append({"stage": "cleansing", "rule": rule_name, "error": str(e)})

        # STAGE B: FEATURE RULES
        for i, rule in enumerate(feature_rules, start=1):
            rule_name = rule.get("feature_name", f"feature_rule_{i}")
            code_str = rule.get("code_snippet")
            if not code_str: continue
            try:
                exec(code_str, self.exec_globals, local_scope)
                execution_log["features_executed"] += 1
            except Exception as e:
                execution_log["features_failed"] += 1
                execution_log["errors"].append({"stage": "feature_engineering", "rule": rule_name, "error": str(e)})

        return local_scope["df"], execution_log
