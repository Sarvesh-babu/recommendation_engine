"""
Layer 1 Refinement: Sandboxed AST Code Safety Validator & Compiler

"""

import ast
from typing import Tuple, List, Dict, Any

# Forbidden modules that could compromise server security or execute shell commands
FORBIDDEN_MODULES = {
    'os', 'sys', 'subprocess', 'requests', 'shutil', 'socket', 
    'http', 'pathlib', 'urllib', 'ftplib', 'builtins', 'importlib'
}

# Forbidden builtin function calls
FORBIDDEN_FUNCTIONS = {'exec', 'eval', 'open', '__import__', 'compile', 'input', 'globals', 'locals'}


def is_code_safe(code_snippet: str) -> Tuple[bool, str]:
    """
    Parses a python code string into an Abstract Syntax Tree (AST) and verifies security.
    """
    if not code_snippet or not str(code_snippet).strip():
        return True, "Empty snippet"
        
    try:
        tree = ast.parse(code_snippet)
    except SyntaxError as e:
        return False, f"SyntaxError: {e.msg} at line {e.lineno}"
    except Exception as e:
        return False, f"AST Parse Error: {e}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                base_module = alias.name.split('.')[0]
                if base_module in FORBIDDEN_MODULES:
                    return False, f"Security Violation: Forbidden module import '{alias.name}'"

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                base_module = node.module.split('.')[0]
                if base_module in FORBIDDEN_MODULES:
                    return False, f"Security Violation: Forbidden module import from '{node.module}'"

        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in FORBIDDEN_FUNCTIONS:
                    return False, f"Security Violation: Forbidden function call '{node.func.id}()'"
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr in ('system', 'popen', 'spawn', 'exec'):
                    return False, f"Security Violation: Forbidden attribute call '.{node.func.attr}()'"

        elif isinstance(node, ast.Attribute):
            if node.attr.startswith('__') and node.attr.endswith('__') and node.attr not in ('__name__', '__doc__'):
                return False, f"Security Violation: Forbidden internal attribute access '{node.attr}'"

    return True, "Passed AST Inspection"


def filter_safe_rules(rules: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Filters LLM-generated rules using AST validation.
    """
    approved_rules = []
    rejected_rules = []

    for rule in rules:
        snippet = rule.get("code_snippet", "")
        is_safe, reason = is_code_safe(snippet)
        
        rule_copy = dict(rule)
        rule_copy["ast_pass"] = is_safe
        rule_copy["ast_reason"] = reason

        if is_safe:
            approved_rules.append(rule_copy)
        else:
            rejected_rules.append(rule_copy)

    return approved_rules, rejected_rules
