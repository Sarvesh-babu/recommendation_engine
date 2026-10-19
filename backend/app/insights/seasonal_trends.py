"""6. Seasonal Trend Detector.

Raw monthly counts confound seasonality with traffic (a busy month inflates
every pair), so everything is normalised by baskets per month B_m.

Pair seasonality (top pairs by support, months with B_m > 0):
    rate_m      n_m(A,B) / B_m
    index_m     rate_m / mean(rate)            100 = average month
    CV          std(rate) / mean(rate)          population std (ddof=0)
    expected_m  n(A,B) · B_m / N                counts if the pair had no seasonality
    χ² test     observed n_m vs expected_m  →  p-value

    seasonal    p < alpha                       (monthly rate differs from volume-proportional)
    evergreen   not seasonal and present in ≥ 60% of months
    sporadic    otherwise
χ² is unreliable when expected counts are < 5; such pairs are flagged
`low_expected_counts` so the classification can be read with caution.

Category momentum:
    share_m     baskets containing the category in month m / B_m
    slope       OLS slope of share_m on month number (percentage points / month)
    trend       rising / falling if p(slope) < alpha, else stable
"""
from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from app.insights.basket_index import UNKNOWN_CATEGORY, BasketIndex


def compute_seasonal_trends(
    index: BasketIndex,
    top_n_pairs: int = 15,
    min_pair_support: int = 5,
    alpha: float = 0.05,
) -> dict[str, Any]:
    times = index.basket_time.dropna()
    if times.empty:
        return {"error": "No valid timestamps in transaction data"}

    month_of = times.dt.to_period("M")
    months = pd.period_range(month_of.min(), month_of.max(), freq="M")
    if len(months) < 3:
        return {"error": "Need at least 3 months of data for seasonal analysis"}
    labels = [str(m) for m in months]
    pos = {m: i for i, m in enumerate(months)}

    baskets_per_month = np.zeros(len(months))
    revenue_per_month = np.zeros(len(months))
    pair_monthly: dict[tuple, np.ndarray] = defaultdict(lambda: np.zeros(len(months)))
    cat_monthly: dict[str, np.ndarray] = defaultdict(lambda: np.zeros(len(months)))

    pair_total: Counter = Counter()
    for tid, m in month_of.items():
        i = pos[m]
        items = index.baskets[tid]
        baskets_per_month[i] += 1
        revenue_per_month[i] += index.basket_value.get(tid, 0.0)
        for pair in combinations(sorted(items), 2):
            pair_monthly[pair][i] += 1
            pair_total[pair] += 1
        for c in {index.cat(p) for p in items} - {UNKNOWN_CATEGORY}:
            cat_monthly[c][i] += 1

    active = baskets_per_month > 0
    n_active = int(active.sum())
    if n_active < 3:
        return {"error": "Need at least 3 months with transactions for seasonal analysis"}
    n_dated = float(baskets_per_month.sum())

    top_pairs = [(p, s) for p, s in pair_total.most_common() if s >= min_pair_support][:top_n_pairs]
    trends = [_pair_trend(index, pair, s, pair_monthly[pair], baskets_per_month, active, n_dated, labels, alpha)
              for pair, s in top_pairs]

    categories = [_category_trend(c, counts, baskets_per_month, active, labels, alpha)
                  for c, counts in sorted(cat_monthly.items())]

    return {
        "months": labels,
        "monthly_baskets": {labels[i]: int(baskets_per_month[i]) for i in range(len(labels))},
        "monthly_revenue": {labels[i]: round(float(revenue_per_month[i]), 2) for i in range(len(labels))},
        "active_months": n_active,
        "partial_months": _partial_months(times, labels),
        "trends": trends,
        "category_trends": categories,
        "summary": {
            "evergreen_count": sum(t["trend_type"] == "evergreen" for t in trends),
            "seasonal_count": sum(t["trend_type"] == "seasonal" for t in trends),
            "sporadic_count": sum(t["trend_type"] == "sporadic" for t in trends),
            "rising_categories": [c["category"] for c in categories if c["trend"] == "rising"],
            "falling_categories": [c["category"] for c in categories if c["trend"] == "falling"],
        },
        "params": {"min_pair_support": min_pair_support, "alpha": alpha},
    }


def _pair_trend(index, pair, support, counts, baskets, active, n_dated, labels, alpha) -> dict:
    a, b = pair
    rates = np.divide(counts, baskets, out=np.zeros_like(counts), where=baskets > 0)
    active_rates = rates[active]
    mean_rate = float(active_rates.mean())
    cv = float(active_rates.std() / mean_rate) if mean_rate > 0 else 0.0
    seasonal_index = np.divide(rates, mean_rate, out=np.zeros_like(rates), where=active) * 100

    expected = support * baskets[active] / n_dated
    observed = counts[active]
    chi2, p_value = stats.chisquare(observed, expected)
    months_present = int((observed > 0).sum())
    presence = months_present / int(active.sum())

    if p_value < alpha:
        trend_type = "seasonal"
    elif presence >= 0.6:
        trend_type = "evergreen"
    else:
        trend_type = "sporadic"

    peak = int(np.argmax(np.where(active, seasonal_index, -np.inf)))
    return {
        "product_a_id": a,
        "product_a_name": index.label(a),
        "product_b_id": b,
        "product_b_name": index.label(b),
        "total_support": int(support),
        "months_present": months_present,
        "total_months": int(active.sum()),
        "presence_ratio_pct": round(presence * 100, 1),
        "coefficient_of_variation": round(cv, 3),
        "chi2": round(float(chi2), 3),
        "p_value": round(float(p_value), 4),
        "low_expected_counts": bool((expected < 5).any()),
        "trend_type": trend_type,
        "peak_month": labels[peak],
        "peak_index": round(float(seasonal_index[peak]), 1),
        "monthly_counts": {labels[i]: int(counts[i]) for i in range(len(labels))},
        "monthly_index": {labels[i]: round(float(seasonal_index[i]), 1) for i in range(len(labels))},
    }


def _category_trend(category, counts, baskets, active, labels, alpha) -> dict:
    share = np.divide(counts, baskets, out=np.zeros_like(counts), where=baskets > 0) * 100
    x = np.arange(len(labels))[active]
    y = share[active]
    reg = stats.linregress(x, y)
    mean_share = float(y.mean())
    slope = float(reg.slope)
    p = float(reg.pvalue) if not np.isnan(reg.pvalue) else 1.0
    trend = ("rising" if slope > 0 else "falling") if p < alpha else "stable"
    peak = int(np.argmax(np.where(active, share, -np.inf)))
    return {
        "category": category,
        "mean_share_pct": round(mean_share, 2),
        "slope_pp_per_month": round(slope, 3),
        "relative_change_per_month_pct": round(slope / mean_share * 100, 2) if mean_share else 0.0,
        "r_squared": round(float(reg.rvalue ** 2), 3),
        "p_value": round(p, 4),
        "trend": trend,
        "peak_month": labels[peak],
        "monthly_share_pct": {labels[i]: round(float(share[i]), 2) for i in range(len(labels))},
    }


def _partial_months(times: pd.Series, labels: list[str]) -> list[str]:
    """First/last month are partial when data starts after day 1 / ends before month end."""
    first, last = times.min(), times.max()
    partial = []
    if first.day > 1:
        partial.append(labels[0])
    if last.day < last.days_in_month and labels[-1] not in partial:
        partial.append(labels[-1])
    return partial
