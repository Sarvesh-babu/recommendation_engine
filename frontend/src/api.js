const BASE = "/api";

export async function asJson(res) {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

export function listIndustries() {
  return fetch(`${BASE}/industries`).then(asJson);
}

export function uploadAndValidate(industry, files) {
  const form = new FormData();
  for (const [name, file] of Object.entries(files)) {
    if (file) form.append(name, file);
  }
  return fetch(`${BASE}/pipeline/upload?industry=${encodeURIComponent(industry)}`, {
    method: "POST",
    body: form,
  }).then(asJson);
}

export function getModelOptions() {
  return fetch(`${BASE}/model-options`).then(asJson);
}

export function startTraining(runId, modelConfig) {
  return fetch(`${BASE}/pipeline/train/${runId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(modelConfig || {}),
  }).then(asJson);
}

export function listRuns() {
  return fetch(`${BASE}/pipeline/runs`).then(asJson);
}

export function getRunStatus(runId) {
  return fetch(`${BASE}/pipeline/status/${runId}`).then(asJson);
}

export function getMetrics(runId) {
  return fetch(`${BASE}/pipeline/metrics/${runId}`).then(asJson);
}

export function getEda(runId) {
  const q = runId ? `?run_id=${runId}` : "";
  return fetch(`${BASE}/pipeline/eda${q}`).then(asJson);
}

export function listCustomers(runId) {
  return fetch(`${BASE}/pipeline/customers/${runId}`).then(asJson);
}

export function listProducts(runId) {
  return fetch(`${BASE}/pipeline/products/${runId}`).then(asJson);
}

export function getPersonalized(customerId, runId) {
  const q = runId ? `?run_id=${runId}` : "";
  return fetch(`${BASE}/recommendations/personalized/${encodeURIComponent(customerId)}${q}`).then(asJson);
}

export function getFrequentlyBoughtTogether(productId, runId) {
  const q = runId ? `?run_id=${runId}` : "";
  return fetch(`${BASE}/recommendations/frequently-bought-together/${encodeURIComponent(productId)}${q}`).then(
    asJson
  );
}

export function getCartRecommendations(productIds, runId, customerLabel) {
  const q = runId ? `?run_id=${runId}` : "";
  return fetch(`${BASE}/recommendations/cart${q}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ product_ids: productIds, customer_label: customerLabel || null }),
  }).then(asJson);
}

export function getSampleCarts(runId, n) {
  const params = new URLSearchParams();
  if (runId) params.set("run_id", runId);
  if (n) params.set("n", n);
  const q = params.toString() ? `?${params.toString()}` : "";
  return fetch(`${BASE}/recommendations/sample-carts${q}`).then(asJson);
}

export function getPopular(segment, runId) {
  const params = new URLSearchParams();
  if (segment) params.set("segment", segment);
  if (runId) params.set("run_id", runId);
  const q = params.toString() ? `?${params.toString()}` : "";
  return fetch(`${BASE}/recommendations/popular${q}`).then(asJson);
}

export function excelExportUrl(runId) {
  return `${BASE}/export/excel/${runId}`;
}

export function getRunFileList(runId) {
  return fetch(`${BASE}/layer1/files/${runId}`).then(asJson);
}

export function refineSingleFileLayer1(runId, datasetName) {
  return fetch(`${BASE}/layer1/refine-file/${runId}/${datasetName}`, { method: "POST" }).then(asJson);
}

export function applyLayer1Rules(runId, datasetName, approvedRules) {
  return fetch(`${BASE}/layer1/apply/${runId}/${datasetName}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(approvedRules),
  }).then(asJson);
}
