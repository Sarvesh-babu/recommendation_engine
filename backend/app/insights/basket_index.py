"""Shared basket index for the Insights layer.

Every insight module works off the same basket-level facts (which products
were bought together, by whom, at what price, when). Building them once here
keeps the six modules consistent with each other — the same N, the same
supports, the same prices — and avoids recomputing pair counts six times.

Notation used throughout the layer:
    N          number of baskets (distinct transaction_id)
    n(A)       baskets containing product A
    n(A,B)     baskets containing both A and B
    P(A)       n(A) / N
    conf(A→B)  P(B | A) = n(A,B) / n(A)
    lift(A,B)  P(A,B) / (P(A)·P(B)) = n(A,B)·N / (n(A)·n(B))   (symmetric)

Significance: under independence n(A,B) ~ Hypergeometric(N, n(A), n(B)), so
the one-sided Fisher p-value for a positive association is
    p = P(X ≥ n(A,B)).
Thousands of pairs are tested at once, so p-values are adjusted with
Benjamini–Hochberg (q-values) and a pair is "significant" when q < alpha.
Without this, most "associations" with support 2–3 are chance.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats

UNKNOWN_CATEGORY = "Unknown"
_CATEGORY_COLUMNS = ["category", "product_category", "Category", "dept", "department"]


def lift(n_ab: int, n_a: int, n_b: int, n_total: int) -> float:
    """lift = P(A,B) / (P(A)·P(B)). 1.0 means independence."""
    if n_a == 0 or n_b == 0 or n_total == 0:
        return 0.0
    return n_ab * n_total / (n_a * n_b)


def confidence(n_ab: int, n_a: int) -> float:
    """conf(A→B) = P(B | A) = n(A,B) / n(A)."""
    return n_ab / n_a if n_a else 0.0


def association_p_values(n_ab, n_a, n_b, n_total) -> tuple[np.ndarray, np.ndarray]:
    """One-sided hypergeometric p-values for over- and under-association.

    p_over  = P(X ≥ n_ab),  p_under = P(X ≤ n_ab),  X ~ Hypergeom(N, n_a, n_b).
    """
    n_ab, n_a, n_b = (np.asarray(x, dtype=float) for x in (n_ab, n_a, n_b))
    p_over = stats.hypergeom.sf(n_ab - 1, n_total, n_a, n_b)
    p_under = stats.hypergeom.cdf(n_ab, n_total, n_a, n_b)
    return np.clip(p_over, 0.0, 1.0), np.clip(p_under, 0.0, 1.0)


def bh_adjust(p_values) -> np.ndarray:
    """Benjamini–Hochberg FDR-adjusted q-values (monotone, capped at 1)."""
    p = np.asarray(p_values, dtype=float)
    m = p.size
    if m == 0:
        return p
    order = np.argsort(p)
    ranked = p[order] * m / np.arange(1, m + 1)
    q_sorted = np.minimum.accumulate(ranked[::-1])[::-1]
    q = np.empty(m)
    q[order] = np.minimum(q_sorted, 1.0)
    return q


@dataclass(frozen=True)
class PairStat:
    support: int
    lift: float
    p_value: float
    q_value: float


@dataclass
class BasketIndex:
    lines: pd.DataFrame                     # one row per transaction line, normalised
    baskets: dict[str, frozenset]           # transaction_id -> products in basket
    basket_value: pd.Series                 # transaction_id -> Σ quantity × unit price
    basket_time: pd.Series                  # transaction_id -> timestamp (NaT if unparseable)
    product_support: Counter                # n(A)
    pair_support: Counter                   # n(A,B), keys are sorted (A, B) with A < B
    product_customers: dict[str, set]       # A -> customers who bought A
    product_revenue: dict[str, float]       # A -> realised revenue Σ quantity × unit price
    price: dict[str, float]                 # A -> reference unit price
    name: dict[str, str]
    category: dict[str, str]
    has_categories: bool
    total_revenue: float
    n_baskets: int = field(init=False)
    n_customers: int = field(init=False)
    pair_stats: dict[tuple, PairStat] = field(init=False)

    def __post_init__(self):
        self.n_baskets = len(self.baskets)
        self.n_customers = int(self.lines["customer_id"].nunique())
        pairs = list(self.pair_support)
        n_ab = [self.pair_support[p] for p in pairs]
        n_a = [self.product_support[a] for a, _ in pairs]
        n_b = [self.product_support[b] for _, b in pairs]
        p_over, _ = association_p_values(n_ab, n_a, n_b, self.n_baskets)
        q = bh_adjust(p_over)
        self.pair_stats = {
            pair: PairStat(n_ab[i], lift(n_ab[i], n_a[i], n_b[i], self.n_baskets), float(p_over[i]), float(q[i]))
            for i, pair in enumerate(pairs)
        }

    def significant_pairs(self, alpha: float = 0.05, min_support: int = 2) -> list[tuple[tuple, PairStat]]:
        """Positively associated pairs with BH q-value < alpha, strongest support first."""
        out = [(p, s) for p, s in self.pair_stats.items() if s.q_value < alpha and s.support >= min_support and s.lift > 1]
        out.sort(key=lambda x: (x[1].support, x[1].lift), reverse=True)
        return out

    # ── accessors ──────────────────────────────────────────
    def support(self, a: str, b: str) -> int:
        return self.pair_support.get((a, b) if a < b else (b, a), 0)

    def lift(self, a: str, b: str) -> float:
        return lift(self.support(a, b), self.product_support[a], self.product_support[b], self.n_baskets)

    def confidence(self, a: str, b: str) -> float:
        """P(b | a)."""
        return confidence(self.support(a, b), self.product_support[a])

    def label(self, pid: str) -> str:
        return self.name.get(pid, pid)

    def cat(self, pid: str) -> str:
        return self.category.get(pid, UNKNOWN_CATEGORY)


def build_basket_index(txn: pd.DataFrame, products_df: pd.DataFrame | None) -> BasketIndex:
    products_df = products_df if products_df is not None else pd.DataFrame(columns=["product_id"])

    lines = txn.copy()
    for col in ("transaction_id", "product_id", "customer_id"):
        if col in lines.columns:
            lines[col] = lines[col].astype(str)
    if "customer_id" not in lines.columns:
        lines["customer_id"] = lines["transaction_id"]
    lines["quantity"] = (
        pd.to_numeric(lines["quantity"], errors="coerce").fillna(1.0) if "quantity" in lines.columns else 1.0
    )

    products = products_df.copy()
    if "product_id" in products.columns:
        products["product_id"] = products["product_id"].astype(str)
        products = products.drop_duplicates("product_id").set_index("product_id")

    price = _reference_prices(lines, products)

    # Unit price actually paid on each line; falls back to the reference price.
    paid = pd.to_numeric(lines["price"], errors="coerce") if "price" in lines.columns else pd.Series(np.nan, index=lines.index)
    lines["unit_price"] = paid.fillna(lines["product_id"].map(price)).fillna(0.0)
    lines["line_value"] = lines["quantity"] * lines["unit_price"]

    lines["timestamp"] = (
        pd.to_datetime(lines["timestamp"], errors="coerce") if "timestamp" in lines.columns else pd.NaT
    )

    baskets = {tid: frozenset(g) for tid, g in lines.groupby("transaction_id")["product_id"]}
    basket_value = lines.groupby("transaction_id")["line_value"].sum()
    basket_time = lines.groupby("transaction_id")["timestamp"].min()

    product_support: Counter = Counter()
    pair_support: Counter = Counter()
    for items in baskets.values():
        product_support.update(items)
        if len(items) > 1:
            pair_support.update(combinations(sorted(items), 2))

    cat_col = next((c for c in _CATEGORY_COLUMNS if c in products.columns), None)
    category = (
        products[cat_col].dropna().astype(str).to_dict() if cat_col else {}
    )
    name = products["name"].dropna().astype(str).to_dict() if "name" in products.columns else {}

    product_customers: dict[str, set] = defaultdict(set)
    for pid, cid in zip(lines["product_id"], lines["customer_id"]):
        product_customers[pid].add(cid)

    product_revenue = lines.groupby("product_id")["line_value"].sum().astype(float).to_dict()

    return BasketIndex(
        lines=lines,
        baskets=baskets,
        basket_value=basket_value.astype(float),
        basket_time=basket_time,
        product_support=product_support,
        pair_support=pair_support,
        product_customers=dict(product_customers),
        product_revenue=product_revenue,
        price=price,
        name=name,
        category=category,
        has_categories=bool(cat_col),
        total_revenue=float(lines["line_value"].sum()),
    )


def _reference_prices(lines: pd.DataFrame, products: pd.DataFrame) -> dict[str, float]:
    """Reference unit price per product.

    Order of precedence (same as the Cart Companion spec, formula 2.1):
    catalogue price → mean paid price in transactions → dataset average price.
    """
    price: dict[str, float] = {}
    if "price" in products.columns:
        catalogue = pd.to_numeric(products["price"], errors="coerce").dropna()
        price.update({str(k): float(v) for k, v in catalogue.items()})
    if "price" in lines.columns:
        paid = pd.to_numeric(lines["price"], errors="coerce")
        mean_paid = paid.groupby(lines["product_id"]).mean().dropna()
        for pid, p in mean_paid.items():
            price.setdefault(pid, float(p))
    if price:
        fallback = float(np.mean(list(price.values())))
        for pid in lines["product_id"].unique():
            price.setdefault(pid, fallback)
    return price
