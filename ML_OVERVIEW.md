# ML Layer Overview

This document explains the machine-learning side of the Recommendation Accelerator: what each model does, why it was chosen, what preprocessing/feature engineering feeds it, how recommendations are evaluated, and how to read the resulting metrics. For the product/task roadmap see [TASKS.md](TASKS.md).

---

## 1. End-to-end flow

The pipeline runs in two phases so the UI can show data-quality feedback before committing to (slower) training. Orchestration lives in [runner.py](backend/app/pipeline/runner.py).

```
Upload CSVs
   │  POST /pipeline/upload
   ▼
Validate schema + thresholds  ──► ingestion.py
   ▼
Run EDA (sparsity, top products, basket sizes, time series)  ──► eda.py
   ▼
[UI: review EDA, pick model variants per category]  ──► ModelSettingsPage
   │  POST /pipeline/train/{run_id}
   ▼
Feature engineering (behavioral/temporal + optional groups)  ──► features.py
   ▼
Train models: ALS/BPR/content-based, neural hybrid, Apriori/FP-Growth, popularity  ──► models.py, deep_model.py
   ▼
Offline evaluation (temporal leave-out vs. popularity baseline)  ──► evaluation.py
   ▼
Attach "why recommended" explanations + display names  ──► explain.py
   ▼
Persist to SQLite, keyed by run_id  ──► store.py
   ▼
Serve via REST: personalized / frequently-bought-together / popular / cart  ──► main.py
```

Cart recommendations are a separate, on-demand path: no training step, just a co-occurrence aggregation over the run's raw transactions, computed fresh on each request (`POST /recommendations/cart` in [main.py](backend/app/main.py)).

The industry-pack layer ([retail/pack.py](backend/app/industry_packs/retail/pack.py)) keeps vertical-specific assumptions (e.g. retail's `category`/`brand`/`segment` columns) out of the core pipeline, so `eda.py`, `models.py`, and `evaluation.py` stay industry-agnostic and only call into the pack for things like "which column should we segment popularity by."

---

## 2. Preprocessing & validation

[ingestion.py](backend/app/pipeline/ingestion.py) does adaptive ingestion in two passes:

1. **Schema check** — `transactions`, `customers`, `products` are required with a fixed minimal column set ([schemas.py](backend/app/schemas.py)). `sessions`, `returns`, `search_logs`, `promotions` are optional; if present their columns are validated, if absent they're silently skipped (no error) — feature engineering gates on presence later, so a missing optional file just means fewer feature groups, not a failed run.
2. **Volume gate** — hard-errors if there are fewer than 50 transaction rows, 5 distinct customers, or 5 distinct products ([config.py](backend/app/config.py)). This exists because matrix factorization and association-rule mining are meaningless (and can crash) below a minimum density.

No row-level cleaning (deduplication, outlier removal, imputation) happens beyond what's described in feature engineering below — the system is designed to work with already-reasonably-clean transactional exports, with `pd.to_datetime(..., errors="coerce")` quietly turning unparseable timestamps into `NaT` rather than failing the run.

---

## 3. Feature engineering ([features.py](backend/app/pipeline/features.py))

Two feature groups are always computed from `transactions`:

| Feature group | What it computes | Used by |
|---|---|---|
| **Behavioral** | `total_spend`, `n_orders`, `n_distinct_products` per customer | Neural hybrid side features |
| **Temporal** | `recency_days` since last purchase, per customer | Neural hybrid side features; also conceptually mirrors the recency weighting in popularity ranking |

Four more groups activate **only if their source file was uploaded** (fail-soft adaptive gating — see `build_features`):

| Feature group | Source file | What it computes |
|---|---|---|
| Session affinity | `sessions` | Per (customer, product) view counts, summed to a per-customer total |
| Returns-adjusted demand | `returns` | `net_demand = units_sold - units_returned` per product, surfacing products that sell well but boomerang back |
| Search intent | `search_logs` | Number of searches per customer, a proxy for browsing engagement beyond purchases |
| Promotion sensitivity | `promotions` | Fraction of a customer's purchases that were on a promoted product |

These engineered features were previously computed but unused by any model — the neural hybrid model ([deep_model.py](backend/app/pipeline/deep_model.py)) is what consumes them via `build_side_features`, which assembles them into a customer feature matrix and a product feature matrix (z-score standardized, zero-filled for any feature group that didn't activate), row-aligned to the same customer/product ordering as the interaction matrix.

Product-side features also include `units_sold`, `price` (standardized), and `category_freq` (how common a product's category is in the catalog) — these come straight from `transactions`/`products`, not from `features.py`.

---

## 4. The three recommendation surfaces, and their models

All model variants are listed and selectable per run in [ModelSettingsPage](frontend/src/pages/ModelSettingsPage.jsx), backed by `GET /model-options`. Defaults are marked `"default": True` in [models.py](backend/app/pipeline/models.py).

### 4.1 Personalized ("customers like you" / per-customer top-N)

Built on a **user-item interaction matrix**: rows = customers, columns = products, values = purchase counts (`build_user_item_matrix`). This is implicit feedback — we only observe positive signals (purchases), never explicit ratings or true negatives, which shapes every model choice below.

| Variant | Model | Why this model |
|---|---|---|
| **ALS + neural hybrid re-rank** (default) | Alternating Least Squares matrix factorization, candidates re-ranked by a small neural net | ALS is the standard, well-understood baseline for implicit-feedback CF — fast, scalable, no negative sampling needed at the MF stage. The neural re-rank lets the engineered side features (returns, promos, search, sessions) actually influence ranking, which raw ALS can't use. |
| **ALS only** | Same ALS, no re-rank | Isolates how much the neural re-rank step is actually contributing — useful as an ablation/comparison. |
| **BPR** (Bayesian Personalized Ranking) | Pairwise ranking loss instead of ALS's pointwise reconstruction | Optimizes directly for "rank positives above negatives" rather than reconstructing the (binarized) interaction matrix — often a better match for top-N ranking quality, at the cost of slower, iterative training. |
| **Content-based** | Cosine similarity between a customer's purchase-weighted profile and product metadata (category/brand one-hot + standardized price) | No embeddings or training required, fully interpretable, and works even when collaborative signal is thin — a useful contrast to the CF-based variants. |

**Why ALS specifically, mechanically:** `train_als` scales the matrix by `* 20.0` before fitting — implicit-feedback ALS (Hu, Koren & Volinsky) treats raw counts as a *confidence* signal rather than a preference value, and this scaling factor controls how strongly repeated purchases increase confidence relative to the regularization term.

**Cold-start fallback chain** (`_mf_candidate_recommendations`), applied identically to ALS and BPR:
- ≥3 interactions → MF model generates a shortlist (`candidate_n = top_k × 5`), optionally re-ranked by the neural model.
- 1–2 interactions → too little signal for MF to be reliable, so it falls back to **item-item cosine similarity** (`item_based_cf_scores`) over the products the customer already bought.
- 0 interactions → empty result, filled in by the **popularity** model upstream in `main.py` (`source: "popularity_fallback"` in the API response).

This three-tier fallback is what keeps every customer servable regardless of how much history they have, without forcing every customer through a brittle MF cold-start.

**Neural hybrid re-rank, in detail** ([deep_model.py](backend/app/pipeline/deep_model.py)):
- A small PyTorch model (`NeuralHybridCF`) with learned 32-dim user and item embeddings, plus two linear projections (`cust_proj`, `item_proj`) of the engineered side features into the same embedding space. All four vectors are concatenated and passed through a 2-layer MLP (64 → 32 → 1) to produce a single relevance logit.
- **Training**: implicit feedback again — observed purchases are positives, 4 uniformly-sampled un-owned items per positive are negatives (`NEG_RATIO = 4`), trained with binary cross-entropy (`BCEWithLogitsLoss`) for 5 epochs.
- **Inference**: it never scores the full catalog. It only re-ranks the ALS/BPR shortlist (`score_items`), blending min-max-normalized MF and neural scores 50/50 (`DEEP_MODEL_WEIGHT = 0.5`). This keeps it cheap and means it inherits ALS's candidate generation rather than needing its own retrieval step — by design it has the same cold-start blind spot as ALS, which is why the fallback chain above sits underneath both.

### 4.2 Frequently bought together (FBT)

Anchored on a specific product, ranking *other* products by basket co-purchase strength ([association_rules_fbt](backend/app/pipeline/models.py)).

| Variant | Method | Why |
|---|---|---|
| **Apriori, lift** (default) | Frequent-itemset mining (`mlxtend.apriori`, max itemset size 2) → association rules ranked by **lift** | Lift = `P(A∩B) / (P(A)·P(B))` — how much more likely B is to be bought given A, *relative to B's base rate*. Surfaces rare-but-strong pairings (e.g. a niche accessory) rather than just generically popular items. |
| **Apriori, confidence** | Same mining, ranked by **confidence** = `P(B\|A)` | Favors pairs that are most *reliably* bought together, even if each item individually is common — different business question than lift. |
| **FP-Growth** | Same lift ranking, faster mining algorithm (no candidate generation step) | Same statistical output as Apriori-lift, but scales better as basket count grows. |
| **Raw co-occurrence** | Literal basket co-occurrence counts, no statistical filtering | The simplest possible signal — useful as a sanity baseline or when basket volume is too small for support thresholds to find anything. |

`min_support = max(2 / n_baskets, 0.01)` — adaptive so that small datasets don't get filtered to zero itemsets. Any product the rule-mining step doesn't cover (support/lift threshold not met) falls back to raw co-occurrence counts (`_fill_cooccurrence_fallback`), so every product still gets an FBT list.

**Cart recommendations** reuse the same co-occurrence primitive but aggregate it across *every item currently in the cart* at once (`cart_cooccurrence_recommendations`): a candidate that co-occurs with two cart items outranks one that only co-occurs with one. This is computed live per request from the run's raw transactions — no separate training/persistence step.

### 4.3 Popular

A non-personalized fallback and its own first-class result type.

| Variant | Method | Why |
|---|---|---|
| **Frequency + recency weighted** (default) | Units sold, weighted by `exp(-ln(2) · days_ago / 30)` (30-day half-life exponential decay) | Favors consistent recent best-sellers over historically-popular-but-now-stale products, without a hard cutoff window. |
| **Trending / velocity** | Week-over-week growth: `(recent_7d - prior_7d) / (prior_7d + 1)` | Surfaces fast-rising products even at low absolute volume — a different signal (momentum vs. magnitude) than the default. |

Both variants optionally segment by a retail-pack-provided customer attribute (`segment`, e.g. budget/regular/premium), producing one ranked list per segment plus an `overall` list.

---

## 5. Explainability layer ([explain.py](backend/app/pipeline/explain.py))

Every recommendation gets a human-readable reason attached. This is explicitly a **post-hoc explanation**, not something the models compute internally:

- **Content-based / FBT / popularity**: the reason *is* the literal signal the ranking used (matching category/brand, shared-basket count, best-seller rank).
- **ALS / BPR / neural hybrid**: the reason is the *strongest matching signal found in the customer's history* (e.g. "matches your most-purchased category") — an approximation of whatever latent factors actually drove the score, since matrix-factorization scores aren't directly interpretable. This is a deliberate simplification: it makes the UI trustworthy without claiming the model used that specific reasoning.

---

## 6. Evaluation: how we measure recommendation quality

[evaluation.py](backend/app/pipeline/evaluation.py) implements **temporal leave-out offline evaluation**, the standard methodology for recommender systems when there's no live A/B-testing infrastructure.

### 6.1 Method

1. **Split**: for each customer with ≥2 distinct purchased products, the most recently purchased ~20% of their *distinct products* (`TEST_FRACTION = 0.2`) are held out as the "future" the model shouldn't see. Customers with only one distinct product can't be meaningfully evaluated and are left entirely in training.
2. **Retrain**: the *exact same* pipeline used in production — ALS, item-CF fallback, neural hybrid, and whichever personalized variant the run selected — is retrained from scratch on the train-only data. This is important: it evaluates the real serving pipeline (including its fallback chain), not ALS in isolation.
3. **Score**: for each customer, check whether their held-out products appear in the model's top-K recommendations, computed from the train-only model.
4. **Baseline**: the same check is run against a popularity-only recommender (same bestseller list for everyone) as a reference point.

### 6.2 The metrics, and why each one matters

For K ∈ {5, 10}:

- **Precision@K** = `(# held-out products recommended) / K`
  Of the K slots you showed the customer, what fraction were actually right? This is the metric that matters most for UI real estate — every wrong slot is a wasted impression (or worse, a credibility hit).

- **Recall@K** = `(# held-out products recommended) / (# held-out products total)`
  Of everything the customer actually went on to buy, what fraction did you surface? Recall is naturally capped by `K` relative to how many products were held out per customer, so it's most meaningful as a *relative* (model vs. baseline) measure here, not an absolute target.

- **Hit-rate@K** = `1` if *any* held-out product appears in the top-K, else `0`, averaged across customers.
  The most forgiving and most "business-relevant" metric: did this customer see *at least one* good recommendation? This correlates most directly with "did the recommendation widget feel useful" in practice.

All three are reported for both the model and the popularity baseline, side by side, in the [ValidationPage](frontend/src/pages/ValidationPage.jsx) — both as a bar chart and a table.

### 6.3 How to read the numbers / what "good" looks like

There isn't a single universal target for precision@K — published numbers in recommender-systems literature and case studies vary by an order of magnitude depending on catalog size, interaction sparsity, and time span, so treat any external number as a loose compass rather than a pass/fail bar:

- **Precision@10** on implicit-feedback retail data is commonly reported in the low single digits to ~10% — small, curated catalogs trend toward the higher end of that range; large, sparse catalogs trend toward the lower end.
- **Hit-rate@10** in the 20–50% range is a commonly cited bar for "the recommendation widget is doing useful work" in e-commerce case studies.
- **Recall@10** is typically the smallest-looking number of the three, simply because most customers hold out more products than fit in 10 slots.

Because absolute numbers are so sensitive to dataset shape, **the benchmark this tool actually optimizes for is relative, not absolute**: does the selected model meaningfully beat the popularity baseline, computed with the identical temporal split and the identical metric definitions? That comparison controls for catalog size, sparsity, and time span automatically, which an externally-quoted number can't. A model that's only marginally better than "show everyone the bestseller list" is a signal to revisit the model choice, feature set, or data volume — not to chase a specific external percentage.

`evaluate()` returns `None` when there isn't enough repeat-purchase history to evaluate at all (e.g. every customer bought only one distinct product) — this is a real possibility on small/synthetic datasets and surfaces as "no metrics available" rather than a misleading zero.

---

## 7. Insights surfaced before training (EDA)

[eda.py](backend/app/pipeline/eda.py) runs after validation, before training, specifically so a user can sanity-check the data before paying the cost of training:

- **Sparsity** = `1 - (distinct customer-product pairs) / (n_customers × n_products)` — the single most important number for predicting whether collaborative filtering will work well; very high sparsity (close to 1.0) is a leading indicator of a cold-start-heavy dataset where the fallback chain (item-CF, popularity) will carry more weight than ALS itself.
- **Basket size distribution** — directly informs whether FBT/association-rule mining has enough multi-item baskets to find anything beyond the co-occurrence fallback.
- **Top products, price distribution, transactions over time, category/segment breakdowns** (the latter two only if the retail pack finds `category`/`segment` columns) — general data-quality and shape checks, industry-agnostic except for the two pack-provided breakdowns.

---

## 8. Known boundaries (see [TASKS.md](TASKS.md) for the live roadmap)

- Models are trained in **batch** per run, served from a SQLite-backed precomputed table — there is no live/online scoring path yet.
- Evaluation is **offline only** (temporal leave-out against historical purchases); there's no online A/B testing or served-recommendation logging yet.
- The dataset in `backend/data/sample/retail/` is **synthetic** (`generate_synthetic_data.py`), so absolute metric values from it should be read as illustrative of the methodology, not as a claim about real-world performance.
