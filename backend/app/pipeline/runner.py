"""Orchestrates a pipeline run in two phases so the UI can show EDA before
committing to (slower) model training:

  prepare_run -> ingest -> validate -> EDA                  (status: eda_ready)
  train_models -> features -> train -> evaluate -> persist  (status: completed)

Industry-agnostic except for the single call into the registry-resolved pack.
"""
from app.pipeline import deep_model as deep_model_mod
from app.pipeline import eda as eda_mod
from app.pipeline import evaluation as evaluation_mod
from app.pipeline import explain as explain_mod
from app.pipeline import features as features_mod
from app.pipeline import models as models_mod
from app.pipeline import store
from app.pipeline.ingestion import ValidationError, load_uploaded_files
from app.registry import get_pack


def prepare_run(run_id: str, industry: str, file_paths: dict[str, str]) -> None:
    store.create_run(run_id, industry)
    try:
        pack = get_pack(industry)
        dataframes = load_uploaded_files(file_paths)

        warnings = pack.validate_extension(dataframes["products"], dataframes["customers"])
        eda_summary = eda_mod.run_eda(dataframes)
        eda_summary["warnings"] = warnings

        category_key = pack.category_key(dataframes["products"])
        if category_key:
            eda_summary["category_breakdown"] = eda_mod.category_breakdown(
                dataframes["transactions"], dataframes["products"], category_key
            )
        segment_key_for_eda = pack.popularity_segment_key(dataframes["customers"])
        if segment_key_for_eda:
            eda_summary["segment_breakdown"] = eda_mod.segment_breakdown(
                dataframes["transactions"], dataframes["customers"], segment_key_for_eda
            )

        customer_names = explain_mod.build_name_map(dataframes["customers"], "customer_id")
        product_names = explain_mod.build_name_map(dataframes["products"], "product_id")
        store.write_name_maps(run_id, customer_names, product_names)

        store.mark_eda_ready(run_id, eda_summary)
    except ValidationError as e:
        store.mark_run_failed(run_id, str(e))
    except Exception as e:  # surfaced via GET /pipeline/status, not swallowed
        store.mark_run_failed(run_id, f"{type(e).__name__}: {e}")


def _resolve_variant(model_config: dict | None, category: str, dispatch: dict, options: list[dict]) -> str:
    default_name = next(opt["name"] for opt in options if opt["default"])
    if not model_config:
        return default_name
    name = model_config.get(category)
    return name if name in dispatch else default_name


def train_models(run_id: str, industry: str, file_paths: dict[str, str], model_config: dict | None = None) -> None:
    store.mark_training_started(run_id, model_config)
    try:
        pack = get_pack(industry)
        dataframes = load_uploaded_files(file_paths)
        features = features_mod.build_features(dataframes)

        txn = dataframes["transactions"]
        matrix, customers, products, cust_idx, prod_idx = models_mod.build_user_item_matrix(txn)
        als_model = models_mod.train_als(matrix)
        item_similarity = models_mod.item_based_cf_scores(matrix)

        cust_feat, prod_feat = deep_model_mod.build_side_features(features, dataframes, customers, products)
        deep_model = deep_model_mod.train_neural_model(matrix, cust_feat, prod_feat)

        personalized_variant = _resolve_variant(
            model_config, "personalized", models_mod.PERSONALIZED_DISPATCH, models_mod.PERSONALIZED_MODEL_OPTIONS
        )
        personalized = models_mod.PERSONALIZED_DISPATCH[personalized_variant](
            matrix,
            customers,
            products,
            cust_idx,
            prod_idx,
            als_model,
            item_similarity,
            deep_model=deep_model,
            cust_feat=cust_feat,
            prod_feat=prod_feat,
            products_df=dataframes["products"],
        )

        fbt_variant = _resolve_variant(model_config, "fbt", models_mod.FBT_DISPATCH, models_mod.FBT_MODEL_OPTIONS)
        fbt = models_mod.FBT_DISPATCH[fbt_variant](txn)

        popular_variant = _resolve_variant(
            model_config, "popular", models_mod.POPULAR_DISPATCH, models_mod.POPULAR_MODEL_OPTIONS
        )
        segment_key = pack.popularity_segment_key(dataframes["customers"])
        popularity = models_mod.POPULAR_DISPATCH[popular_variant](txn, dataframes["customers"], segment_key)

        metrics = evaluation_mod.evaluate(dataframes, features, personalized_variant=personalized_variant)

        product_names = explain_mod.build_name_map(dataframes["products"], "product_id")
        personalized_enriched = explain_mod.enrich_personalized(
            personalized, txn, dataframes["products"], product_names, personalized_variant
        )
        fbt_enriched = explain_mod.enrich_fbt(fbt, txn, product_names)
        popularity_enriched = explain_mod.enrich_popularity(popularity, product_names, popular_variant)

        store.write_personalized(run_id, personalized_enriched)
        store.write_fbt(run_id, fbt_enriched)
        store.write_popularity(run_id, popularity_enriched)
        store.mark_training_completed(run_id, metrics)
    except ValidationError as e:
        store.mark_run_failed(run_id, str(e))
    except Exception as e:  # surfaced via GET /pipeline/status, not swallowed
        store.mark_run_failed(run_id, f"{type(e).__name__}: {e}")
