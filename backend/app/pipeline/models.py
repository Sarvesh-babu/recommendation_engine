"""Model training for the three result types, each with selectable variants.

personalized -> default is ALS matrix factorization (implicit feedback)
                shortlists, re-ranked by a neural hybrid model (deep_model.py)
                blending learned embeddings with engineered side features
                when one was trained; falls back to item-based CF
                cosine-similarity for users the candidate generator can't
                confidently score (too few interactions), and popularity as
                the last resort. Alternates: ALS without re-rank, BPR
                (Bayesian Personalized Ranking) instead of ALS, and a
                content-based variant using product metadata similarity.
frequently bought together -> default is association rules (Apriori) over
                baskets, ranked by lift. Alternates: same Apriori ranked by
                confidence, FP-Growth as a faster itemset miner, and raw
                co-occurrence counts as a standalone ranking.
popular        -> default is frequency + recency weighted ranking,
                optionally segmented by a retail-pack-provided customer
                attribute. Alternate: week-over-week trending velocity.
"""
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix

from app.pipeline import deep_model as deep_model_mod

MIN_INTERACTIONS_FOR_ALS = 3
DEEP_MODEL_WEIGHT = 0.5
CANDIDATE_MULTIPLIER = 5


def build_user_item_matrix(
    txn: pd.DataFrame,
    customers_df: pd.DataFrame | None = None,
    products_df: pd.DataFrame | None = None
):
    customers = sorted(txn["customer_id"].unique())
    products = sorted(txn["product_id"].unique())
    cust_idx = {c: i for i, c in enumerate(customers)}
    prod_idx = {p: i for i, p in enumerate(products)}

    has_qty = "quantity" in txn.columns
    counts = txn.groupby(["customer_id", "product_id"]).agg(
        count=("quantity", "sum") if has_qty else ("customer_id", "count")
    ).reset_index()

    weights = np.ones(len(counts), dtype=np.float32)

    # Apply exponential time decay if timestamps exist
    if "timestamp" in txn.columns:
        txn_copy = txn.copy()
        txn_copy["ts"] = pd.to_datetime(txn_copy["timestamp"], errors="coerce")
        max_ts = txn_copy["ts"].max()
        if pd.notna(max_ts):
            time_agg = txn_copy.groupby(["customer_id", "product_id"])["ts"].max().reset_index()
            counts = counts.merge(time_agg, on=["customer_id", "product_id"], how="left")
            days_ago = (max_ts - counts["ts"]).dt.total_seconds() / (24 * 3600)
            decay = np.exp(-0.005 * days_ago.fillna(0.0).to_numpy())
            weights *= decay

    # Apply Layer 1 log-monetary multiplier if present
    if customers_df is not None and not customers_df.empty and "user_monetary_total_log" in customers_df.columns:
        monetary_map = customers_df.set_index("customer_id")["user_monetary_total_log"].to_dict()
        cust_monetary = counts["customer_id"].map(monetary_map).fillna(1.0).to_numpy()
        weights *= np.maximum(0.5, cust_monetary)

    values = counts["count"].values * weights
    rows = counts["customer_id"].map(cust_idx)
    cols = counts["product_id"].map(prod_idx)
    matrix = csr_matrix((values, (rows, cols)), shape=(len(customers), len(products)))
    return matrix, customers, products, cust_idx, prod_idx


def train_als(matrix: csr_matrix, factors: int = 32, iterations: int = 15):
    from implicit.als import AlternatingLeastSquares

    model = AlternatingLeastSquares(factors=factors, iterations=iterations, regularization=0.1)
    model.fit(matrix * 20.0)  # confidence scaling for implicit feedback
    return model


def train_bpr(matrix: csr_matrix, factors: int = 32, iterations: int = 100):
    from implicit.bpr import BayesianPersonalizedRanking

    model = BayesianPersonalizedRanking(factors=factors, iterations=iterations, regularization=0.01)
    binarized = (matrix > 0).astype(np.float32)
    model.fit(binarized)
    return model


def item_based_cf_scores(matrix: csr_matrix) -> csr_matrix:
    """Item-item cosine similarity over the user-item matrix, used as a
    fallback for customers with too little signal for the main candidate
    generator to be reliable."""
    from sklearn.preprocessing import normalize

    item_vectors = normalize(matrix.T, axis=1)
    similarity = item_vectors @ item_vectors.T
    return similarity.tocsr()


def _minmax(arr: np.ndarray) -> np.ndarray:
    if len(arr) == 0:
        return arr
    lo, hi = arr.min(), arr.max()
    if hi - lo < 1e-9:
        return np.zeros_like(arr, dtype=float)
    return (arr - lo) / (hi - lo)


def _mf_candidate_recommendations(
    mf_model,
    matrix,
    customers,
    products,
    cust_idx,
    item_similarity,
    deep_model,
    cust_feat: np.ndarray | None,
    prod_feat: np.ndarray | None,
    apply_rerank: bool,
    top_k: int,
    deep_model_weight: float = 0.25,
) -> dict[str, list[str]]:
    """Shared candidate-generation + fallback chain for matrix-factorization
    based personalized variants (ALS, BPR): MF shortlist -> optional
    deep-model re-rank -> item-CF fallback for sparse users -> empty for
    customers with zero interactions (filled in by popularity upstream)."""
    results: dict[str, list[str]] = {}
    interaction_counts = np.asarray((matrix > 0).sum(axis=1)).ravel()

    for customer, ci in cust_idx.items():
        n_interactions = interaction_counts[ci]
        if n_interactions >= MIN_INTERACTIONS_FOR_ALS:
            candidate_n = min(top_k * CANDIDATE_MULTIPLIER, len(products))
            item_ids, mf_scores = mf_model.recommend(
                ci, matrix[ci], N=candidate_n, filter_already_liked_items=True
            )
            if apply_rerank and deep_model is not None and len(item_ids) and deep_model_weight > 0.0:
                deep_scores = deep_model_mod.score_items(deep_model, ci, item_ids, cust_feat, prod_feat)
                blended = _minmax(mf_scores) * (1.0 - deep_model_weight) + _minmax(deep_scores) * deep_model_weight
                order = np.argsort(blended)[::-1][:top_k]
                results[customer] = [products[item_ids[o]] for o in order]
            else:
                results[customer] = [products[i] for i in item_ids[:top_k]]
        elif n_interactions > 0:
            owned = matrix[ci].indices
            scores = np.asarray(item_similarity[owned].sum(axis=0)).ravel()
            scores[owned] = -1
            top_items = np.argsort(scores)[::-1][:top_k]
            results[customer] = [products[i] for i in top_items if scores[i] > 0]
        else:
            results[customer] = []
    return results


def personalized_als_neural_hybrid(
    matrix, customers, products, cust_idx, prod_idx, als_model, item_similarity,
    deep_model=None, cust_feat=None, prod_feat=None, top_k: int = 10,
    deep_model_weight: float = 0.25, **_ignored,
) -> dict[str, list[str]]:
    return _mf_candidate_recommendations(
        als_model, matrix, customers, products, cust_idx, item_similarity,
        deep_model, cust_feat, prod_feat, apply_rerank=True, top_k=top_k,
        deep_model_weight=deep_model_weight,
    )


def personalized_als_only(
    matrix, customers, products, cust_idx, prod_idx, als_model, item_similarity,
    deep_model=None, cust_feat=None, prod_feat=None, top_k: int = 10, **_ignored,
) -> dict[str, list[str]]:
    return _mf_candidate_recommendations(
        als_model, matrix, customers, products, cust_idx, item_similarity,
        deep_model, cust_feat, prod_feat, apply_rerank=False, top_k=top_k,
    )


def personalized_bpr(
    matrix, customers, products, cust_idx, prod_idx, als_model, item_similarity,
    deep_model=None, cust_feat=None, prod_feat=None, top_k: int = 10, **_ignored,
) -> dict[str, list[str]]:
    bpr_model = train_bpr(matrix)
    return _mf_candidate_recommendations(
        bpr_model, matrix, customers, products, cust_idx, item_similarity,
        deep_model, cust_feat, prod_feat, apply_rerank=True, top_k=top_k,
    )


def personalized_content_based(
    matrix, customers, products, cust_idx, prod_idx, als_model, item_similarity,
    deep_model=None, cust_feat=None, prod_feat=None, top_k: int = 10,
    products_df: pd.DataFrame | None = None, **_ignored,
) -> dict[str, list[str]]:
    """Profile each customer as the (purchase-weighted) mean of their
    purchased products' content vectors (category/brand one-hot + scaled
    price), then rank all products by cosine similarity to that profile.
    Customers with zero purchases get an empty result (filled in by
    popularity upstream, same as the other variants)."""
    from sklearn.preprocessing import normalize

    content = _product_content_matrix(products, products_df)
    content_norm = normalize(content, axis=1)

    results: dict[str, list[str]] = {}
    for customer, ci in cust_idx.items():
        owned = matrix[ci].indices
        weights = matrix[ci].data
        if len(owned) == 0:
            results[customer] = []
            continue
        profile = np.average(content_norm[owned], axis=0, weights=weights).reshape(1, -1)
        profile_norm = normalize(profile, axis=1)
        scores = (content_norm @ profile_norm.T).ravel()
        scores[owned] = -1
        top_items = np.argsort(scores)[::-1][:top_k]
        results[customer] = [products[i] for i in top_items if scores[i] > -1]
    return results


def _product_content_matrix(products: list[str], products_df: pd.DataFrame) -> np.ndarray:
    df = products_df.set_index("product_id").reindex(products)
    blocks = []
    for col in ("category", "brand"):
        if col in df.columns:
            blocks.append(pd.get_dummies(df[col].fillna("__missing__")).to_numpy(dtype=float))
    if "price" in df.columns:
        price = df["price"].fillna(df["price"].mean()).to_numpy(dtype=float).reshape(-1, 1)
        price_std = (price - price.mean()) / (price.std() + 1e-9)
        blocks.append(price_std)
    if not blocks:
        return np.ones((len(products), 1))
    return np.concatenate(blocks, axis=1)


PERSONALIZED_DISPATCH = {
    "als_neural_hybrid": personalized_als_neural_hybrid,
    "als_only": personalized_als_only,
    "bpr": personalized_bpr,
    "content_based": personalized_content_based,
}

PERSONALIZED_MODEL_OPTIONS = [
    {
        "name": "als_neural_hybrid",
        "label": "ALS + neural hybrid re-rank",
        "description": "ALS matrix factorization shortlist, re-ranked by a neural model blending learned embeddings with engineered features (sessions, returns, search, promotions).",
        "default": True,
    },
    {
        "name": "als_only",
        "label": "ALS only (no re-rank)",
        "description": "Pure ALS matrix factorization scores, without the neural re-ranking step.",
        "default": False,
    },
    {
        "name": "bpr",
        "label": "Bayesian Personalized Ranking (BPR)",
        "description": "An alternative implicit-feedback matrix factorization, optimized directly for ranking rather than rating reconstruction.",
        "default": False,
    },
    {
        "name": "content_based",
        "label": "Content-based (product metadata)",
        "description": "Profiles each customer by the category/brand/price of products they've bought, and recommends similar products. No embeddings or training required.",
        "default": False,
    },
]


def association_rules_fbt(txn: pd.DataFrame, top_k: int = 10, metric: str = "lift", miner: str = "apriori") -> dict[str, list[str]]:
    """Frequently-bought-together pairs via frequent-itemset mining over
    baskets, falling back to raw co-occurrence counts when the basket count
    is too small for the support threshold to find anything."""
    from mlxtend.frequent_patterns import apriori, association_rules, fpgrowth
    from mlxtend.preprocessing import TransactionEncoder

    baskets = txn.groupby("transaction_id")["product_id"].apply(list).tolist()
    n_baskets = len(baskets)
    if n_baskets == 0:
        return {}

    te = TransactionEncoder()
    onehot = te.fit_transform(baskets)
    basket_df = pd.DataFrame(onehot, columns=te.columns_)

    min_support = max(2 / n_baskets, 0.01)
    mine_fn = fpgrowth if miner == "fpgrowth" else apriori
    try:
        freq_items = mine_fn(basket_df, min_support=min_support, use_colnames=True, max_len=2)
        min_threshold = 1.0 if metric == "lift" else 0.3
        rules = association_rules(freq_items, metric=metric, min_threshold=min_threshold)
    except Exception:
        rules = pd.DataFrame()

    results: dict[str, list[tuple[str, float]]] = {}
    for _, row in rules.iterrows():
        if len(row["antecedents"]) != 1:
            continue
        antecedent = next(iter(row["antecedents"]))
        for consequent in row["consequents"]:
            results.setdefault(antecedent, []).append((consequent, row[metric]))

    fbt = {p: [c for c, _ in sorted(v, key=lambda x: -x[1])[:top_k]] for p, v in results.items()}
    return _fill_cooccurrence_fallback(txn, fbt, top_k)


def fbt_apriori_lift(txn: pd.DataFrame, top_k: int = 10) -> dict[str, list[str]]:
    return association_rules_fbt(txn, top_k=top_k, metric="lift", miner="apriori")


def fbt_apriori_confidence(txn: pd.DataFrame, top_k: int = 10) -> dict[str, list[str]]:
    return association_rules_fbt(txn, top_k=top_k, metric="confidence", miner="apriori")


def fbt_fpgrowth(txn: pd.DataFrame, top_k: int = 10) -> dict[str, list[str]]:
    return association_rules_fbt(txn, top_k=top_k, metric="lift", miner="fpgrowth")


def _cooccurrence_counts(txn: pd.DataFrame, products: list[str] | None = None) -> dict[str, dict[str, int]]:
    """Raw basket co-occurrence counts: for each product, how many times
    each other product appeared in the same basket."""
    basket_groups = txn.groupby("transaction_id")["product_id"].apply(set)
    cooccur: dict[str, dict[str, int]] = {}
    for basket in basket_groups:
        for p in basket:
            if products is not None and p not in products:
                continue
            for q in basket:
                if q == p:
                    continue
                cooccur.setdefault(p, {}).setdefault(q, 0)
                cooccur[p][q] += 1
    return cooccur


def _fill_cooccurrence_fallback(txn: pd.DataFrame, fbt: dict[str, list[str]], top_k: int) -> dict[str, list[str]]:
    """Products with no association rule above the lift threshold still
    get an entry, built from raw basket co-occurrence counts."""
    all_products = txn["product_id"].unique()
    missing = [p for p in all_products if p not in fbt]
    if not missing:
        return fbt

    cooccur = _cooccurrence_counts(txn, products=missing)
    for p in missing:
        pairs = cooccur.get(p, {})
        top = sorted(pairs.items(), key=lambda x: -x[1])[:top_k]
        fbt[p] = [c for c, _ in top]
    return fbt


def fbt_cooccurrence(txn: pd.DataFrame, top_k: int = 10) -> dict[str, list[str]]:
    """Standalone raw co-occurrence ranking for every product, with no
    Apriori/FP-Growth step at all."""
    all_products = txn["product_id"].unique()
    cooccur = _cooccurrence_counts(txn)
    fbt: dict[str, list[str]] = {}
    for p in all_products:
        pairs = cooccur.get(p, {})
        top = sorted(pairs.items(), key=lambda x: -x[1])[:top_k]
        fbt[p] = [c for c, _ in top]
    return fbt


def cart_cooccurrence_recommendations(
    txn: pd.DataFrame, cart_product_ids: list[str], top_k: int = 10
) -> list[dict]:
    """Aggregates co-occurrence signal across every product currently in
    the cart, so a candidate that co-occurs with two cart items (e.g.
    goggles, with both swimwear and a cap in the cart) outranks one that
    only co-occurs with a single cart item. Computed on demand from a
    run's raw transactions -- no training/persistence involved."""
    cart_set = set(cart_product_ids)
    cooccur = _cooccurrence_counts(txn, products=list(cart_set))

    aggregated: dict[str, dict[str, int]] = {}
    for cart_item in cart_set:
        for candidate, count in cooccur.get(cart_item, {}).items():
            if candidate in cart_set:
                continue
            aggregated.setdefault(candidate, {})[cart_item] = count

    ranked = sorted(aggregated.items(), key=lambda kv: (-len(kv[1]), -sum(kv[1].values())))[:top_k]
    return [{"product_id": candidate, "contributing_cart_items": contributions} for candidate, contributions in ranked]


FBT_DISPATCH = {
    "apriori_lift": fbt_apriori_lift,
    "apriori_confidence": fbt_apriori_confidence,
    "fpgrowth": fbt_fpgrowth,
    "cooccurrence": fbt_cooccurrence,
}

FBT_MODEL_OPTIONS = [
    {
        "name": "apriori_lift",
        "label": "Association rules (Apriori, lift)",
        "description": "Apriori itemset mining over baskets, ranked by lift -- favors rare-but-strong associations over frequently-co-bought items.",
        "default": True,
    },
    {
        "name": "apriori_confidence",
        "label": "Association rules (Apriori, confidence)",
        "description": "Same Apriori mining, ranked by confidence instead -- favors items most reliably bought together, even if each is individually common.",
        "default": False,
    },
    {
        "name": "fpgrowth",
        "label": "FP-Growth",
        "description": "A faster itemset-mining algorithm than Apriori, same lift-based ranking -- useful for larger basket counts.",
        "default": False,
    },
    {
        "name": "cooccurrence",
        "label": "Raw co-occurrence counts",
        "description": "Simple basket co-occurrence frequency with no statistical filtering -- the most literal 'bought together' signal.",
        "default": False,
    },
]


def popularity_ranking(txn: pd.DataFrame, customers: pd.DataFrame, segment_key: str | None, top_k: int = 10) -> dict:
    txn = txn.copy()
    txn["timestamp"] = pd.to_datetime(txn["timestamp"], errors="coerce")
    now = txn["timestamp"].max()
    halflife_days = 30.0

    txn["recency_weight"] = 1.0
    valid = txn["timestamp"].notna()
    txn.loc[valid, "recency_weight"] = np.exp(
        -np.log(2) * (now - txn.loc[valid, "timestamp"]).dt.days.clip(lower=0) / halflife_days
    )
    txn["weighted_score"] = txn["quantity"] * txn["recency_weight"]

    overall = (
        txn.groupby("product_id")["weighted_score"].sum().sort_values(ascending=False).head(top_k).index.tolist()
    )
    result = {"overall": overall}

    if segment_key and segment_key in customers.columns:
        merged = txn.merge(customers[["customer_id", segment_key]], on="customer_id", how="left")
        for seg, group in merged.groupby(segment_key):
            ranked = group.groupby("product_id")["weighted_score"].sum().sort_values(ascending=False)
            result[f"segment:{seg}"] = ranked.head(top_k).index.tolist()

    return result


def popularity_trending_velocity(
    txn: pd.DataFrame, customers: pd.DataFrame, segment_key: str | None, top_k: int = 10
) -> dict:
    """Ranks products by week-over-week growth: (recent 7 days - prior 7
    days) / (prior 7 days + 1), so fast-rising products surface even if
    their absolute volume is still small."""
    txn = txn.copy()
    txn["timestamp"] = pd.to_datetime(txn["timestamp"], errors="coerce")
    txn = txn.dropna(subset=["timestamp"])
    now = txn["timestamp"].max()
    recent_start = now - pd.Timedelta(days=7)
    prior_start = now - pd.Timedelta(days=14)

    def _velocity(rows: pd.DataFrame) -> pd.Series:
        recent = rows[rows["timestamp"] > recent_start].groupby("product_id")["quantity"].sum()
        prior = rows[(rows["timestamp"] > prior_start) & (rows["timestamp"] <= recent_start)].groupby(
            "product_id"
        )["quantity"].sum()
        all_products = pd.Index(rows["product_id"].unique())
        recent = recent.reindex(all_products, fill_value=0)
        prior = prior.reindex(all_products, fill_value=0)
        return ((recent - prior) / (prior + 1)).sort_values(ascending=False)

    result = {"overall": _velocity(txn).head(top_k).index.tolist()}

    if segment_key and segment_key in customers.columns:
        merged = txn.merge(customers[["customer_id", segment_key]], on="customer_id", how="left")
        for seg, group in merged.groupby(segment_key):
            result[f"segment:{seg}"] = _velocity(group).head(top_k).index.tolist()

    return result


POPULAR_DISPATCH = {
    "recency_weighted": popularity_ranking,
    "trending_velocity": popularity_trending_velocity,
}

POPULAR_MODEL_OPTIONS = [
    {
        "name": "recency_weighted",
        "label": "Frequency + recency weighted",
        "description": "Total units sold, weighted by an exponential recency decay (30-day halflife) -- favors consistent best-sellers.",
        "default": True,
    },
    {
        "name": "trending_velocity",
        "label": "Trending / velocity",
        "description": "Ranks by week-over-week growth in sales rather than absolute volume -- surfaces fast-rising products instead of perennial best-sellers.",
        "default": False,
    },
]
