import { asJson } from "../api";

const BASE = "/api/insights";

export function getAllInsights(runId) {
  return fetch(`${BASE}/all/${runId}`).then(asJson);
}

export function getPromotionOptimizer(runId, assumptions) {
  const params = new URLSearchParams(
    Object.entries(assumptions).filter(([k]) => k !== "bundle_pairs").map(([k, v]) => [k, String(v)])
  );
  return fetch(`${BASE}/promotion-optimizer/${runId}?${params}`).then(asJson);
}
