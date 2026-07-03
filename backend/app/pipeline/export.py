"""Optional secondary output: a formatted dump of the same result-store
tables an API consumer would otherwise fetch via /recommendations/*.
"""
import pandas as pd

from app.config import RUNS_DIR
from app.pipeline import store


def _format_recommendations(items: list) -> str:
    """items is a list of {product_id, name, reason} dicts (current
    format) or plain product_id strings (older runs, pre-explainability)."""
    parts = []
    for item in items:
        if isinstance(item, dict):
            parts.append(f"{item.get('name', item.get('product_id'))} -- {item.get('reason', '')}")
        else:
            parts.append(str(item))
    return "; ".join(parts)


def write_excel_export(run_id: str) -> str:
    tables = store.all_tables_for_export(run_id)
    out_path = RUNS_DIR / run_id / "export.xlsx"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        for sheet_name, rows in tables.items():
            df = pd.DataFrame(rows)
            if not df.empty and "recommendations" in df.columns:
                df["recommendations"] = df["recommendations"].apply(_format_recommendations)
            df.to_excel(writer, sheet_name=sheet_name[:31], index=False)

    return str(out_path)
