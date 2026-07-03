import shutil
import uuid

import pandas as pd
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import OPTIONAL_FILES, REQUIRED_FILES, RUNS_DIR, TOP_K_DEFAULT
from app.pipeline import explain as explain_mod
from app.pipeline import models as models_mod
from app.pipeline import store
from app.pipeline.export import write_excel_export
from app.pipeline.runner import prepare_run, train_models
from app.registry import available_industries
from app.schemas import CartRequest, TrainRequest

app = FastAPI(title="Recommendation Accelerator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
store.init_db()


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
    """Phase 1: save uploads, validate, and compute EDA. Does not train
    models -- call POST /pipeline/train/{run_id} once the EDA looks good."""
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
    """Phase 2: train ALS + neural hybrid + FBT + popularity, and run the
    offline evaluation. Requires phase 1 (EDA) to have completed first.
    Optionally accepts a JSON body selecting which algorithm variant to use
    per category -- see GET /model-options for valid names."""
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(404, f"Unknown run_id '{run_id}'")
    if run["status"] != "eda_ready":
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
    if not run or not run.get("eda"):
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
def get_cart_recommendations(payload: CartRequest, run_id: str | None = None):
    """Recommends companion products for an entire cart at once, computed
    on demand from the run's raw transactions -- no training step, no
    precomputed table. Decoupled from the personalized/fbt/popular flow."""
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

    return {
        "run_id": rid,
        "computed_at": run["computed_at"] if run else None,
        "cart": [{"product_id": pid, "name": product_names.get(pid, pid)} for pid in payload.product_ids],
        "customer_label": payload.customer_label,
        "recommendations": enriched,
    }


def _sample_carts(
    txn: pd.DataFrame, customer_names: dict[str, str], product_names: dict[str, str], n: int = 3
) -> list[dict]:
    """Stands in for a real "fetch this customer's current cart" API:
    picks n distinct customers' most recent multi-item basket and presents
    it as their "current cart". Swap this out for a real external call
    later -- the response shape is what the frontend actually depends on."""
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
    """Mock "fetch a customer's live cart" API: returns n example carts
    drawn from this run's real purchase history, for demoing the cart
    recommendations page without manual entry."""
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
