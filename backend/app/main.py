import shutil
import uuid
import time
from typing import Any
from dotenv import load_dotenv
load_dotenv()

import pandas as pd
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import OPTIONAL_FILES, REQUIRED_FILES, RUNS_DIR, TOP_K_DEFAULT
from app.pipeline import explain as explain_mod
from app.pipeline import models as models_mod
from app.pipeline import store
from app.pipeline.cart_insights import compute_cart_insights, recommended_shipping_threshold
from app.pipeline.export import write_excel_export
from app.pipeline.runner import prepare_run, train_models
from app.pipeline.layer1_orchestrator import run_layer1_refinement
from app.insights import service as insights_service
from app.insights.router import router as insights_router
from app.registry import available_industries
from app.schemas import CartRequest, TrainRequest

app = FastAPI(title="Recommendation Accelerator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://127.0.0.1:5173", "http://127.0.0.1:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)
store.init_db()
app.include_router(insights_router)

_layer1_cache = {}


@app.get("/industries")
def list_industries():
    return {"industries": available_industries()}


def _file_paths_for_run(run_id: str) -> dict[str, str]:
    run_dir = RUNS_DIR / run_id
    file_paths: dict[str, str] = {}
    for name in [*REQUIRED_FILES, *OPTIONAL_FILES]:
        path = run_dir / f"{name}.csv"
        if path.exists():
            file_paths[name] = str(path)
    return file_paths


@app.post("/pipeline/upload")
async def upload_and_validate(
    background_tasks: BackgroundTasks,
    industry: str,
    transactions: UploadFile = File(...),
    customers: UploadFile = File(...),
    products: UploadFile = File(...),
    sessions: UploadFile | None = File(None),
    returns: UploadFile | None = File(None),
    search_logs: UploadFile | None = File(None),
    promotions: UploadFile | None = File(None),
):
    run_id = uuid.uuid4().hex[:12]
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    uploads = {
        "transactions": transactions,
        "customers": customers,
        "products": products,
        "sessions": sessions,
        "returns": returns,
        "search_logs": search_logs,
        "promotions": promotions,
    }
    file_paths: dict[str, str] = {}
    for name, upload in uploads.items():
        if upload is None:
            continue
        dest = run_dir / f"{name}.csv"
        with open(dest, "wb") as f:
            shutil.copyfileobj(upload.file, f)
        file_paths[name] = str(dest)

    background_tasks.add_task(prepare_run, run_id, industry, file_paths)
    return {"run_id": run_id, "status": "validating"}


@app.get("/model-options")
def model_options():
    return {
        "personalized": models_mod.PERSONALIZED_MODEL_OPTIONS,
        "fbt": models_mod.FBT_MODEL_OPTIONS,
        "popular": models_mod.POPULAR_MODEL_OPTIONS,
    }


@app.post("/pipeline/train/{run_id}")
def start_training(run_id: str, background_tasks: BackgroundTasks, model_config: TrainRequest | None = None):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(404, f"Unknown run_id '{run_id}'")
    if run["status"] not in ("eda_ready", "completed"):
        raise HTTPException(409, f"Run '{run_id}' is not ready for training (status={run['status']})")

    dispatches = {
        "personalized": models_mod.PERSONALIZED_DISPATCH,
        "fbt": models_mod.FBT_DISPATCH,
        "popular": models_mod.POPULAR_DISPATCH,
    }
    config_dict = model_config.model_dump(exclude_none=True) if model_config else {}
    for category, name in config_dict.items():
        if name not in dispatches[category]:
            raise HTTPException(400, f"Unknown '{category}' model variant '{name}'")

    file_paths = _file_paths_for_run(run_id)
    background_tasks.add_task(train_models, run_id, run["industry"], file_paths, config_dict or None)
    return {"run_id": run_id, "status": "training"}


@app.get("/pipeline/runs")
def list_runs():
    return {"runs": store.list_runs()}


@app.get("/pipeline/status/{run_id}")
def pipeline_status(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(404, f"Unknown run_id '{run_id}'")
    return run


@app.get("/pipeline/metrics/{run_id}")
def pipeline_metrics(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(404, f"Unknown run_id '{run_id}'")
    if run["status"] != "completed":
        raise HTTPException(409, f"Run '{run_id}' is not completed (status={run['status']})")
    if not run.get("metrics"):
        raise HTTPException(404, f"No evaluation metrics available for run '{run_id}'")
    return {"run_id": run_id, "computed_at": run["computed_at"], **run["metrics"]}


def _resolve_run_id(run_id: str | None) -> str:
    if run_id:
        return run_id
    latest = store.latest_completed_run()
    if not latest:
        raise HTTPException(404, "No completed pipeline run yet")
    return latest["run_id"]


@app.get("/pipeline/eda")
def get_eda(run_id: str | None = None):
    rid = _resolve_run_id(run_id)
    run = store.get_run(rid)
    if not run:
        raise HTTPException(404, f"No run found for '{rid}'")

    file_paths = _file_paths_for_run(rid)
    if file_paths:
        try:
            import json
            from app.pipeline.ingestion import load_uploaded_files
            from app.pipeline import eda as eda_mod
            current_dfs = load_uploaded_files(file_paths)
            raw_schema_path = RUNS_DIR / rid / "raw_columns.json"
            raw_schemas = None
            if raw_schema_path.exists():
                with open(raw_schema_path, "r", encoding="utf-8") as f:
                    raw_schemas = json.load(f)
            fresh_eda = eda_mod.run_eda(current_dfs, raw_schemas=raw_schemas)
            return {"run_id": rid, "computed_at": time.time(), **fresh_eda}
        except Exception as e:
            print(f"Dynamic EDA computation error: {e}")

    if not run.get("eda"):
        raise HTTPException(404, f"No EDA available for run '{rid}'")
    return {"run_id": rid, "computed_at": run["computed_at"], **run["eda"]}


@app.get("/pipeline/customers/{run_id}")
def list_customers(run_id: str):
    customer_names, _ = store.get_name_maps(run_id)
    return {"customers": [{"customer_id": cid, "name": name} for cid, name in customer_names.items()]}


@app.get("/pipeline/products/{run_id}")
def list_products(run_id: str):
    _, product_names = store.get_name_maps(run_id)
    return {"products": [{"product_id": pid, "name": name} for pid, name in product_names.items()]}


@app.get("/recommendations/personalized/{customer_id}")
def get_personalized(customer_id: str, run_id: str | None = None):
    rid = _resolve_run_id(run_id)
    run = store.get_run(rid)
    customer_names, _ = store.get_name_maps(rid)
    items = store.get_personalized(rid, customer_id)
    if items is None:
        items = store.get_popularity(rid, "overall") or []
        source = "popularity_fallback"
    else:
        source = "personalized"
    return {
        "customer_id": customer_id,
        "customer_name": customer_names.get(customer_id, customer_id),
        "run_id": rid,
        "computed_at": run["computed_at"] if run else None,
        "source": source,
        "recommendations": items[:TOP_K_DEFAULT],
    }


@app.get("/recommendations/frequently-bought-together/{product_id}")
def get_fbt(product_id: str, run_id: str | None = None):
    rid = _resolve_run_id(run_id)
    run = store.get_run(rid)
    _, product_names = store.get_name_maps(rid)
    items = store.get_fbt(rid, product_id) or []
    return {
        "product_id": product_id,
        "product_name": product_names.get(product_id, product_id),
        "run_id": rid,
        "computed_at": run["computed_at"] if run else None,
        "recommendations": items[:TOP_K_DEFAULT],
    }


@app.post("/recommendations/cart")
def get_cart_recommendations(
    payload: CartRequest,
    run_id: str | None = None,
    free_shipping_threshold: float | None = Query(None, gt=0),
):
    if not payload.product_ids:
        raise HTTPException(400, "cart must contain at least one product_id")

    rid = _resolve_run_id(run_id)
    run = store.get_run(rid)
    file_paths = _file_paths_for_run(rid)
    if "transactions" not in file_paths:
        raise HTTPException(404, f"No transactions file on disk for run '{rid}'")

    txn = pd.read_csv(file_paths["transactions"])
    _, product_names = store.get_name_maps(rid)

    ranked = models_mod.cart_cooccurrence_recommendations(txn, payload.product_ids, top_k=TOP_K_DEFAULT)
    enriched = explain_mod.enrich_cart(ranked, product_names)

    # Cart Companion insights, computed on the Insights layer's shared basket index
    insights = {}
    try:
        index = insights_service.get_index_or_build(rid, txn)
        if free_shipping_threshold is not None:
            threshold, source = free_shipping_threshold, "request"
        else:
            threshold, source = recommended_shipping_threshold(index)
        insights = compute_cart_insights(
            index=index,
            cart_product_ids=payload.product_ids,
            recommendations=enriched,
            free_shipping_threshold=threshold,
            threshold_source=source,
        )
    except Exception as e:
        print(f"Cart insights computation warning: {e}")

    final_recommendations = insights.pop("recommendations", enriched) if insights else enriched

    return {
        "run_id": rid,
        "computed_at": run["computed_at"] if run else None,
        "cart": [{"product_id": pid, "name": product_names.get(pid, pid)} for pid in payload.product_ids],
        "customer_label": payload.customer_label,
        "recommendations": final_recommendations,
        "insights": insights,
    }


def _sample_carts(
    txn: pd.DataFrame, customer_names: dict[str, str], product_names: dict[str, str], n: int = 3
) -> list[dict]:
    basket_sizes = txn.groupby("transaction_id").size()
    multi_item = basket_sizes[basket_sizes >= 2].index
    candidate_baskets = multi_item if len(multi_item) > 0 else basket_sizes.index

    txn_sorted = txn[txn["transaction_id"].isin(candidate_baskets)].sort_values("timestamp", ascending=False)
    carts: list[dict] = []
    seen_customers: set[str] = set()
    for transaction_id, group in txn_sorted.groupby("transaction_id", sort=False):
        customer_id = group["customer_id"].iloc[0]
        if customer_id in seen_customers:
            continue
        seen_customers.add(customer_id)
        product_ids = group["product_id"].unique().tolist()
        carts.append(
            {
                "customer_id": customer_id,
                "customer_label": customer_names.get(customer_id, customer_id),
                "cart": [{"product_id": pid, "name": product_names.get(pid, pid)} for pid in product_ids],
            }
        )
        if len(carts) >= n:
            break
    return carts


@app.get("/recommendations/sample-carts")
def get_sample_carts(run_id: str | None = None, n: int = 3):
    rid = _resolve_run_id(run_id)
    file_paths = _file_paths_for_run(rid)
    if "transactions" not in file_paths:
        raise HTTPException(404, f"No transactions file on disk for run '{rid}'")

    txn = pd.read_csv(file_paths["transactions"])
    customer_names, product_names = store.get_name_maps(rid)
    return {"run_id": rid, "carts": _sample_carts(txn, customer_names, product_names, n=n)}


@app.get("/recommendations/popular")
def get_popular(segment: str | None = None, run_id: str | None = None):
    rid = _resolve_run_id(run_id)
    run = store.get_run(rid)
    key = f"segment:{segment}" if segment else "overall"
    items = store.get_popularity(rid, key)
    if items is None:
        items = store.get_popularity(rid, "overall") or []
    return {
        "segment": segment or "overall",
        "run_id": rid,
        "computed_at": run["computed_at"] if run else None,
        "recommendations": items[:TOP_K_DEFAULT],
    }


@app.get("/export/excel/{run_id}")
def export_excel(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(404, f"Unknown run_id '{run_id}'")
    if run["status"] != "completed":
        raise HTTPException(409, f"Run '{run_id}' is not completed (status={run['status']})")
    path = write_excel_export(run_id)
    return FileResponse(path, filename=f"recommendations_{run_id}.xlsx")


@app.get("/")
def root():
    return {
        "service": "Recommendation Accelerator",
        "required_files": REQUIRED_FILES,
        "optional_files": OPTIONAL_FILES,
    }


# ---------------------------------------------------------
# LAYER 1 REFINEMENT ENDPOINTS WITH UNIFIED RULE COUNT & HITL SUPPORT
# ---------------------------------------------------------

@app.get("/layer1/files/{run_id}")
def get_run_file_list(run_id: str):
    file_paths = _file_paths_for_run(run_id)
    if not file_paths:
        raise HTTPException(404, f"No files found for run '{run_id}'")
    return {"run_id": run_id, "files": list(file_paths.keys())}


@app.post("/layer1/refine-file/{run_id}/{dataset_name}")
def refine_single_file_layer1(
    run_id: str,
    dataset_name: str,
    user_data_dict: dict[str, str] | None = None,
    groq_api_key: str | None = None
):
    file_paths = _file_paths_for_run(run_id)
    key = dataset_name.lower()
    if key not in file_paths:
        raise HTTPException(404, f"File '{dataset_name}' not found for run '{run_id}'")

    try:
        dfs = {key: pd.read_csv(file_paths[key])}
        for other_key, path in file_paths.items():
            if other_key != key:
                dfs[other_key] = pd.read_csv(path)

        res = run_layer1_refinement(
            dfs=dfs,
            user_data_dict=user_data_dict,
            api_key=groq_api_key
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/layer1/apply/{run_id}/{dataset_name}")
def apply_human_approved_rules(
    run_id: str,
    dataset_name: str,
    approved_rules: list[dict[str, Any]]
):
    file_paths = _file_paths_for_run(run_id)
    key = dataset_name.lower()
    if key not in file_paths:
        raise HTTPException(404, f"File '{dataset_name}' not found for run '{run_id}'")

    try:
        from app.pipeline.rule_executor import HybridRuleExecutor
        from app.pipeline.cleansing_wrappers import safe_fillna
        from app.pipeline import eda as eda_mod
        from app.pipeline.ingestion import load_uploaded_files
        from app.pipeline.layer1_orchestrator import run_baseline_refinement

        dfs = {key: pd.read_csv(file_paths[key])}
        for other_key, path in file_paths.items():
            if other_key != key:
                dfs[other_key] = pd.read_csv(path)

        # First run baseline transformations (log transforms, datetime parsing, cross-file aggregations, etc.)
        baseline_dfs, _, _ = run_baseline_refinement(
            dfs=dfs,
            primary_file_name=key,
            user_data_dict=None
        )

        for r in approved_rules:
            if "target_dataset" not in r:
                r["target_dataset"] = key

        # Execute approved LLM & statistical rules on top of baseline transformed DataFrames
        executor = HybridRuleExecutor()
        refined_dfs, exec_log = executor.execute_pipeline(baseline_dfs, approved_rules, target_dataset_name=key)

        # Save ALL refined datasets to disk so engineered features on all tables persist
        for d_name, d_df in refined_dfs.items():
            if d_name in file_paths:
                clean_d = safe_fillna(d_df, 0)
                clean_d.to_csv(file_paths[d_name], index=False)

        refined_df = refined_dfs.get(key, list(refined_dfs.values())[0])
        total_rules_applied = len(approved_rules)

        # Re-compute EDA summary on refined disk files
        try:
            current_dataframes = load_uploaded_files(file_paths)
            eda_summary = eda_mod.run_eda(current_dataframes)
            store.mark_eda_ready(run_id, eda_summary)
        except Exception as eda_err:
            print(f"EDA update warning: {eda_err}")

        return {
            "status": "success",
            "message": f"Successfully applied {total_rules_applied} rules to '{dataset_name}.csv'",
            "engineered_columns": exec_log["engineered_columns"],
            "refined_shape": {"rows": len(refined_df), "cols": len(refined_df.columns)},
            "preview_data": safe_fillna(refined_df.head(50), "").to_dict(orient="records"),
            "applied_rule_count": total_rules_applied
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
