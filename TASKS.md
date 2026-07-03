# Rec Engine — Task List

## Already done
- [x] Core pipeline (upload → validate → EDA → train → results) with first set of models: ALS, BPR, item/content-based, neural hybrid, frequently-bought-together, popularity/trending.
- [x] Multi-page frontend with navigation, per-category model selection, and offline evaluation/validation.
- [x] Synthetic data generation (transactions, sessions, returns, search logs, promotions).
- [x] Industry-pack architecture, with retail as the first pack.
- [x] Customer/product display names (instead of raw ids) generated alongside synthetic data, surfaced through the API and used for name-based search in the UI.
- [x] "Why was this recommended" explanation attached to each personalized/FBT/popularity result (post-hoc reasoning based on category/brand match or co-purchase signal, not a live inference layer).
- [x] Cart-based recommendations: a separate page where a manually-built cart of multiple products gets companion-product recommendations, computed on demand from a run's transaction co-occurrence (no retraining), ranked by how many distinct cart items a candidate co-occurs with.
- [x] Mock "fetch a customer's cart" API (`GET /recommendations/sample-carts`) wired into the cart page as one-click sample carts, standing in for a real external cart API.

## To do

### Real data
- [ ] Source a real or realistic dataset to replace the synthetic one.
- [ ] Adapt data ingestion to handle a real-world schema.
- [ ] Re-check EDA and evaluation results hold up on real data.

### More models
- [ ] Add a few additional recommendation approaches (e.g. sequence/session-based, retrieval + re-ranking).
- [ ] Make new models selectable per category alongside existing ones.

### Inference layer
- [ ] Add a real-time scoring path so recommendations can be generated live, not just from precomputed batch runs.
- [ ] Decide how trained models get loaded/served for live requests.
- [ ] Add basic logging of served recommendations for future evaluation.

### Cart-based recommendations
- [ ] Swap the mock sample-carts endpoint for a real external cart API (the frontend call is isolated to one function, `getSampleCarts`, so this is a drop-in change).
- [ ] Consider an association-rules-based variant (beyond raw co-occurrence) once basket volume justifies it.

### LLM-based modeling & inference
- [ ] Explore using an LLM to explain or re-rank existing recommendations (lower-risk first step).
- [ ] Explore an LLM/embedding-based recommender as a model option.

### Polish
- [ ] Add tests around new models and endpoints.
- [ ] Consider expanding beyond the retail industry pack.
- [ ] Update docs/readme as the above lands.
