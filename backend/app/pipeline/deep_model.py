"""Neural hybrid recommender: a small PyTorch model that learns customer and
product embeddings jointly with the side features computed in features.py
(behavioral, temporal, session affinity, returns, search intent, promo
sensitivity) -- the engineered features that were previously unused by any
model. Trained on implicit feedback (observed purchases as positives,
uniform-sampled un-owned items as negatives). Used to re-rank the ALS
candidate list in models.PERSONALIZED_DISPATCH variants, not as a standalone
source -- it has the same cold-start blind spot as ALS for very sparse
customers, which the existing item-CF / popularity fallbacks already cover.
"""
import numpy as np
import pandas as pd

EMBED_DIM = 32
HIDDEN_DIM = 64
EPOCHS = 5
NEG_RATIO = 4
BATCH_SIZE = 1024
LEARNING_RATE = 1e-3


def _indexed_matrix(df: pd.DataFrame, id_col: str, value_cols: list[str], id_order: list[str]) -> np.ndarray:
    out = np.zeros((len(id_order), len(value_cols)), dtype=np.float64)
    if df is None or len(df) == 0 or id_col not in df.columns:
        return out
    sub = df[[id_col] + value_cols].dropna(subset=[id_col]).drop_duplicates(subset=[id_col], keep="last")
    sub = sub.set_index(id_col)
    for col_i, col in enumerate(value_cols):
        out[:, col_i] = sub[col].reindex(id_order).fillna(0.0).to_numpy()
    return out


def _standardize(mat: np.ndarray) -> np.ndarray:
    if mat.shape[1] == 0:
        return mat
    mean = mat.mean(axis=0)
    std = mat.std(axis=0)
    std[std < 1e-9] = 1.0
    return (mat - mean) / std


def build_side_features(
    features: dict,
    dataframes: dict[str, pd.DataFrame],
    customers: list[str],
    products: list[str],
) -> tuple[np.ndarray, np.ndarray]:
    """Assemble per-customer and per-product numeric feature matrices, row
    order aligned to `customers`/`products` (the same order as cust_idx /
    prod_idx), filtering out skewed, constant, and redundant features."""
    from app.pipeline.features import filter_features_for_modeling

    txn = dataframes["transactions"]
    products_df = dataframes.get("products", pd.DataFrame())
    customers_df = dataframes.get("customers", pd.DataFrame())

    beh_cols = [c for c in ["user_monetary_total_log", "user_frequency_count", "user_avg_unit_price", "total_spend", "n_orders", "n_distinct_products"] if c in features["behavioral"].columns]
    temp_cols = [c for c in ["user_recency_days", "recency_days"] if c in features["temporal"].columns]

    cust_blocks = []
    if beh_cols:
        cust_blocks.append(_indexed_matrix(features["behavioral"], "customer_id", beh_cols, customers))
    if temp_cols:
        cust_blocks.append(_indexed_matrix(features["temporal"], "customer_id", temp_cols, customers))
    if "search_intent" in features:
        cust_blocks.append(_indexed_matrix(features["search_intent"], "customer_id", ["n_searches"], customers))
    if "promotion_sensitivity" in features:
        cust_blocks.append(
            _indexed_matrix(features["promotion_sensitivity"], "customer_id", ["promo_purchase_rate"], customers)
        )
    if "session_affinity" in features:
        session_totals = features["session_affinity"].groupby("customer_id")["session_views"].sum().reset_index()
        cust_blocks.append(_indexed_matrix(session_totals, "customer_id", ["session_views"], customers))

    # Dynamically extract and filter numeric side features from customers DataFrame
    if not customers_df.empty and "customer_id" in customers_df.columns:
        cust_clean_cols = filter_features_for_modeling(customers_df, id_cols=["customer_id"])
        if cust_clean_cols:
            cust_blocks.append(_indexed_matrix(customers_df, "customer_id", cust_clean_cols, customers))

    cust_feat_raw = np.concatenate(cust_blocks, axis=1) if cust_blocks else np.zeros((len(customers), 0))
    cust_feat = _standardize(cust_feat_raw)

    sold = txn.groupby("product_id")["quantity"].sum().reset_index().rename(columns={"quantity": "units_sold"})
    prod_blocks = [_indexed_matrix(sold, "product_id", ["units_sold"], products)]
    if "category" in products_df.columns:
        freq = products_df["category"].value_counts(normalize=True)
        cat_freq_df = products_df[["product_id", "category"]].copy()
        cat_freq_df["category_freq"] = cat_freq_df["category"].map(freq)
        prod_blocks.append(_indexed_matrix(cat_freq_df, "product_id", ["category_freq"], products))
    if "returns_adjusted_demand" in features:
        prod_blocks.append(
            _indexed_matrix(features["returns_adjusted_demand"], "product_id", ["net_demand"], products)
        )

    # Dynamically extract and filter numeric side features from products DataFrame
    if not products_df.empty and "product_id" in products_df.columns:
        prod_clean_cols = filter_features_for_modeling(products_df, id_cols=["product_id"])
        if prod_clean_cols:
            prod_blocks.append(_indexed_matrix(products_df, "product_id", prod_clean_cols, products))

    prod_feat_raw = np.concatenate(prod_blocks, axis=1) if prod_blocks else np.zeros((len(products), 0))
    prod_feat = _standardize(prod_feat_raw)

    return cust_feat, prod_feat


def _build_model(n_customers: int, n_products: int, cust_feat_dim: int, prod_feat_dim: int):
    import torch
    from torch import nn

    class NeuralHybridCF(nn.Module):
        def __init__(self):
            super().__init__()
            self.user_emb = nn.Embedding(n_customers, EMBED_DIM)
            self.item_emb = nn.Embedding(n_products, EMBED_DIM)
            self.cust_proj = nn.Linear(cust_feat_dim, EMBED_DIM) if cust_feat_dim else None
            self.item_proj = nn.Linear(prod_feat_dim, EMBED_DIM) if prod_feat_dim else None
            in_dim = EMBED_DIM * (2 + (cust_feat_dim > 0) + (prod_feat_dim > 0))
            self.mlp = nn.Sequential(
                nn.Linear(in_dim, HIDDEN_DIM),
                nn.ReLU(),
                nn.Linear(HIDDEN_DIM, HIDDEN_DIM // 2),
                nn.ReLU(),
                nn.Linear(HIDDEN_DIM // 2, 1),
            )

        def forward(self, user_idx, item_idx, cust_feat, item_feat):
            parts = [self.user_emb(user_idx), self.item_emb(item_idx)]
            if self.cust_proj is not None:
                parts.append(self.cust_proj(cust_feat))
            if self.item_proj is not None:
                parts.append(self.item_proj(item_feat))
            x = torch.cat(parts, dim=-1)
            return self.mlp(x).squeeze(-1)

    return NeuralHybridCF()


def train_neural_model(matrix, cust_feat: np.ndarray, prod_feat: np.ndarray, seed: int = 42):
    """Returns a trained model, or None if there isn't enough signal
    (e.g. an empty interaction matrix) to train on."""
    import torch
    from torch import nn

    n_customers, n_products = matrix.shape
    coo = matrix.tocoo()
    pos_users, pos_items = coo.row, coo.col
    n_pos = len(pos_users)
    if n_pos == 0:
        return None

    rng = np.random.default_rng(seed)
    owned_sets = [set(matrix[u].indices) for u in range(n_customers)]

    model = _build_model(n_customers, n_products, cust_feat.shape[1], prod_feat.shape[1])
    optimizer = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)
    loss_fn = nn.BCEWithLogitsLoss()

    cust_feat_t = torch.tensor(cust_feat, dtype=torch.float32)
    prod_feat_t = torch.tensor(prod_feat, dtype=torch.float32)

    model.train()
    for _epoch in range(EPOCHS):
        perm = rng.permutation(n_pos)
        for start in range(0, n_pos, BATCH_SIZE):
            batch_idx = perm[start : start + BATCH_SIZE]
            u = pos_users[batch_idx]
            i_pos = pos_items[batch_idx]

            neg_items = np.empty((len(batch_idx), NEG_RATIO), dtype=np.int64)
            for row, user in enumerate(u):
                owned = owned_sets[user]
                picked: list[int] = []
                while len(picked) < NEG_RATIO:
                    cand = rng.integers(0, n_products, size=NEG_RATIO * 2)
                    picked.extend(c for c in cand if c not in owned)
                neg_items[row] = picked[:NEG_RATIO]

            users_rep = np.repeat(u, 1 + NEG_RATIO)
            items_rep = np.concatenate([i_pos.reshape(-1, 1), neg_items], axis=1).reshape(-1)
            labels = np.concatenate(
                [np.ones((len(batch_idx), 1)), np.zeros((len(batch_idx), NEG_RATIO))], axis=1
            ).reshape(-1)

            users_t = torch.tensor(users_rep, dtype=torch.long)
            items_t = torch.tensor(items_rep, dtype=torch.long)
            labels_t = torch.tensor(labels, dtype=torch.float32)

            optimizer.zero_grad()
            scores = model(users_t, items_t, cust_feat_t[users_t], prod_feat_t[items_t])
            loss = loss_fn(scores, labels_t)
            loss.backward()
            optimizer.step()

    model.eval()
    return model


def score_items(model, customer_idx: int, item_indices: np.ndarray, cust_feat: np.ndarray, prod_feat: np.ndarray) -> np.ndarray:
    """Score a specific candidate set of items for one customer (used to
    re-rank the ALS shortlist rather than scoring the full catalog)."""
    import torch

    with torch.no_grad():
        n = len(item_indices)
        users_t = torch.full((n,), customer_idx, dtype=torch.long)
        items_t = torch.tensor(item_indices, dtype=torch.long)
        cust_feat_t = torch.tensor(np.tile(cust_feat[customer_idx], (n, 1)), dtype=torch.float32)
        prod_feat_t = torch.tensor(prod_feat[item_indices], dtype=torch.float32)
        scores = model(users_t, items_t, cust_feat_t, prod_feat_t)
    return scores.numpy()
