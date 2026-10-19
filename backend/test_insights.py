"""Quick smoke test against a running backend: all 6 insight modules return data."""
import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8000"
RUN_ID = sys.argv[1] if len(sys.argv) > 1 else "16409be1af8c"

data = json.load(urllib.request.urlopen(f"{BASE}/insights/all/{RUN_ID}"))

for key in ["category_heatmap", "revenue_opportunity", "affinity_network",
            "action_cards", "promotion_optimizer", "seasonal_trends"]:
    assert "error" not in data[key], f"{key}: {data[key].get('error')}"

ch = data["category_heatmap"]
print(f"[1] Category heatmap: {len(ch['categories'])} categories, {ch['total_baskets']} baskets, "
      f"{len(ch['strongest_pairs'])} significant positive pairs")

ro = data["revenue_opportunity"]
print(f"[2] Revenue opportunity: {ro['total_addressable_revenue']:,.2f} addressable "
      f"({ro['addressable_pct_of_revenue']}% of revenue) from {ro['significant_pairs']} significant pairs")

s = data["affinity_network"]["summary"]
print(f"[3] Affinity network: {s['total_edges']} edges | hubs={s['hub_count']} bridges={s['bridge_count']} orphans={s['orphan_count']}")

ac = data["action_cards"]
print(f"[4] Action cards: {ac['total_cards']} cards {ac['by_type']}")

po = data["promotion_optimizer"]
print(f"[5] Promotion optimizer: recommended threshold={po['recommended_threshold']}, "
      f"recommended bundle discount={po['recommended_discount_pct']}")

sm = data["seasonal_trends"]["summary"]
print(f"[6] Seasonal: {sm['evergreen_count']} evergreen, {sm['seasonal_count']} seasonal, {sm['sporadic_count']} sporadic; "
      f"rising={sm['rising_categories']} falling={sm['falling_categories']}")

print("\nAll 6 modules OK")
