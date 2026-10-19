import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getRunFileList, refineSingleFileLayer1, applyLayer1Rules } from "../api";
import { usePipelineStatus } from "../hooks/usePipelineStatus";

export default function Layer1Refinement() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const { run, error: statusError } = usePipelineStatus(runId);
  const [fileList, setFileList] = useState([]);
  const [activeDataset, setActiveDataset] = useState("");
  const [cache, setCache] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Data Dictionary Input State
  const [showDictPanel, setShowDictPanel] = useState(false);
  const [dictInputText, setDictInputText] = useState("");

  // HITL State
  const [selectedRuleIds, setSelectedRuleIds] = useState(new Set());
  const [customCodeMap, setCustomCodeMap] = useState({});
  const [applying, setApplying] = useState(false);
  const [applySuccess, setApplySuccess] = useState(null);

  useEffect(() => {
    if (runId) {
      getRunFileList(runId)
        .then((res) => {
          const files = res?.files || [];
          setFileList(files);
          if (files.length > 0) setActiveDataset(files[0]);
          else setLoading(false);
        })
        .catch((err) => {
          setError(err.message);
          setLoading(false);
        });
    }
  }, [runId]);

  // Keys for persistent lookup
  const cacheKey = `layer1_cache_${runId}_${activeDataset}`;
  const selectionKey = `layer1_selected_${runId}_${activeDataset}`;
  const customCodeKey = `layer1_custom_code_${runId}_${activeDataset}`;

  const syncDatasetState = (datasetResult) => {
    if (!runId || !activeDataset) return;
    const storedSelection = localStorage.getItem(selectionKey);
    const storedCustomCode = localStorage.getItem(customCodeKey);

    if (storedSelection) {
      try {
        setSelectedRuleIds(new Set(JSON.parse(storedSelection)));
      } catch (e) {
        setSelectedRuleIds(new Set());
      }
    } else if (datasetResult) {
      const defaultSet = new Set();
      (datasetResult.llm_recommendations?.feature_engineering_rules || []).forEach((r, idx) => {
        defaultSet.add(r.rule_id || `feat_${idx}`);
      });
      (datasetResult.statistical_validation?.action_proposals || []).forEach((a) => {
        if (a.action_id) defaultSet.add(a.action_id);
      });
      setSelectedRuleIds(defaultSet);
    } else {
      setSelectedRuleIds(new Set());
    }

    if (storedCustomCode) {
      try {
        setCustomCodeMap(JSON.parse(storedCustomCode));
      } catch (e) {
        setCustomCodeMap({});
      }
    } else {
      setCustomCodeMap({});
    }
  };

  const loadRefinementData = (userDict = null, forceRefresh = false) => {
    if (!runId || !activeDataset) return;

    // Fast persistent lookup: avoid re-running backend/LLM if data exists
    if (!forceRefresh && !userDict) {
      const storedCache = sessionStorage.getItem(cacheKey);
      if (storedCache) {
        try {
          const parsedCache = JSON.parse(storedCache);
          setCache((prev) => ({ ...prev, [activeDataset]: parsedCache }));
          syncDatasetState(parsedCache);
          setLoading(false);
          return;
        } catch (e) {
          console.error("Storage parse error:", e);
        }
      }
    }

    setLoading(true);
    refineSingleFileLayer1(runId, activeDataset, userDict)
      .then((res) => {
        setCache((prev) => ({ ...prev, [activeDataset]: res }));
        try {
          sessionStorage.setItem(cacheKey, JSON.stringify(res));
        } catch (e) { }
        syncDatasetState(res);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (runId && activeDataset) {
      if (cache[activeDataset]) {
        syncDatasetState(cache[activeDataset]);
        setLoading(false);
        return;
      }
      loadRefinementData();
    }
  }, [runId, activeDataset]);

  const handleSaveDataDictionary = () => {
    let parsedDict = {};
    try {
      if (dictInputText.trim().startsWith("{")) {
        parsedDict = JSON.parse(dictInputText);
      } else {
        dictInputText.split("\n").forEach((line) => {
          const parts = line.split("=");
          if (parts.length === 2) {
            parsedDict[parts[0].trim()] = parts[1].trim();
          }
        });
      }
      loadRefinementData(parsedDict, true);
      setShowDictPanel(false);
    } catch (e) {
      setError("Invalid format in Data Dictionary input.");
    }
  };

  const currentResult = cache[activeDataset];
  const datasetNameUpper = activeDataset ? activeDataset.toUpperCase() : "";

  // Unified Rule Counts
  const baselineRules = currentResult?.applied_baseline_rules || [];
  const baselineCount = baselineRules.length;
  const tickedCount = selectedRuleIds.size;
  const totalApprovedCount = baselineCount + tickedCount;

  // File Switching Index
  const currentFileIdx = fileList.indexOf(activeDataset);
  const isLastFile = currentFileIdx === fileList.length - 1;
  const nextFileName = !isLastFile ? fileList[currentFileIdx + 1] : null;

  const toggleRule = (ruleId) => {
    const next = new Set(selectedRuleIds);
    if (next.has(ruleId)) next.delete(ruleId);
    else next.add(ruleId);
    setSelectedRuleIds(next);
    try {
      localStorage.setItem(selectionKey, JSON.stringify(Array.from(next)));
    } catch (e) { }
  };

  const toggleAllRules = (selectAll = true) => {
    const next = new Set();
    if (selectAll && currentResult) {
      const features = currentResult.llm_recommendations?.feature_engineering_rules || [];
      features.forEach((rule, idx) => {
        next.add(rule.rule_id || `feat_${idx}`);
      });
      const statActions = currentResult.statistical_validation?.action_proposals || [];
      statActions.forEach((action) => {
        next.add(action.action_id);
      });
    }
    setSelectedRuleIds(next);
    try {
      localStorage.setItem(selectionKey, JSON.stringify(Array.from(next)));
    } catch (e) { }
  };

  const handleCodeChange = (ruleId, newCode) => {
    setCustomCodeMap((prev) => {
      const next = { ...prev, [ruleId]: newCode };
      try {
        localStorage.setItem(customCodeKey, JSON.stringify(next));
      } catch (e) { }
      return next;
    });
  };

  const formatUserFriendlyRule = (ruleStr) => {
    if (ruleStr.startsWith("Cross-File:")) return ruleStr;
    if (ruleStr.includes("log_transform")) return ruleStr.replace("log_transform(", "Log Skewness Reduction on ").replace(") ->", " creates");
    if (ruleStr.includes("parse_datetime")) return ruleStr.replace("parse_datetime_features(", "Extracted Date Features from ").replace(")", "");
    if (ruleStr.includes("impute_median")) return ruleStr.replace("impute_median(", "Filled Missing Values (Median) in ").replace(")", "");
    return ruleStr;
  };

  const handleApplyRules = () => {
    if (!currentResult) return;
    setApplying(true);
    setApplySuccess(null);

    const cleansing = currentResult.llm_recommendations?.cleansing_rules || [];
    const features = currentResult.llm_recommendations?.feature_engineering_rules || [];
    const statActions = currentResult.statistical_validation?.action_proposals || [];

    const approvedRules = [];

    features.forEach((rule, idx) => {
      const id = rule.rule_id || `feat_${idx}`;
      if (selectedRuleIds.has(id)) {
        const finalCode = customCodeMap[id] !== undefined ? customCodeMap[id] : rule.code_snippet;
        approvedRules.push({ ...rule, code_snippet: finalCode });
      }
    });

    statActions.forEach((action) => {
      if (selectedRuleIds.has(action.action_id)) {
        approvedRules.push({
          rule_id: action.action_id,
          action_type: action.action_type,
          target_column: action.target_column,
          code_snippet: action.code_snippet
        });
      }
    });

    cleansing.forEach((rule) => approvedRules.push(rule));

    applyLayer1Rules(runId, activeDataset, approvedRules)
      .then((res) => {
        setApplySuccess(res.message);

        const updatedDatasetCache = {
          ...currentResult,
          preview_data: res.preview_data || currentResult.preview_data,
          engineered_columns: res.engineered_columns || [],
          refined_shape: res.refined_shape || currentResult.refined_shape
        };

        setCache((prev) => ({
          ...prev,
          [activeDataset]: updatedDatasetCache
        }));

        try {
          sessionStorage.setItem(cacheKey, JSON.stringify(updatedDatasetCache));
        } catch (e) { }

        setTimeout(() => {
          if (!isLastFile && nextFileName) {
            setActiveDataset(nextFileName);
            setApplySuccess(null);
          } else {
            navigate(`/eda/${runId}`);
          }
        }, 1200);
      })
      .catch((err) => setError(err.message))
      .finally(() => setApplying(false));
  };

  const getRuleFeatureName = (rule) => {
    if (rule.feature_name) {
      let name = rule.feature_name.trim();
      if (name.includes(" ") && rule.code_snippet) {
        const match = rule.code_snippet.match(/df\s*\[\s*['"]([^'"]+)['"]\s*\]/);
        if (match) return match[1].toLowerCase();
      }
      return name.toLowerCase().replace(/\s+/g, "_");
    }
    if (rule.code_snippet) {
      const match = rule.code_snippet.match(/df\s*\[\s*['"]([^'"]+)['"]\s*\]/);
      if (match) return match[1].toLowerCase();
    }
    return null;
  };

  const getFeatureSummaryStats = () => {
    if (!currentResult?.enriched_data_dictionary?.columns) return null;

    const llmRules = currentResult.llm_recommendations?.feature_engineering_rules || [];
    const uncheckedLLMFeatures = new Set();
    const checkedLLMFeatures = new Set();

    llmRules.forEach((rule, idx) => {
      const ruleId = rule.rule_id || `feat_${idx}`;
      const featName = getRuleFeatureName(rule);
      if (featName) {
        if (selectedRuleIds.has(ruleId)) {
          checkedLLMFeatures.add(featName.toLowerCase());
        } else {
          uncheckedLLMFeatures.add(featName.toLowerCase());
        }
      }
    });

    const optionalCrossFileMetrics = new Set([
      "total_spend", "total_transactions", "avg_order_value",
      "total_units_sold", "total_product_revenue", "price_tier", "price_efficiency",
      "user_order_frequency", "account_tenure_days", "age_group"
    ]);

    const isExcluded = (colName) => {
      const lower = colName.toLowerCase();
      if (checkedLLMFeatures.has(lower)) return false;
      if (uncheckedLLMFeatures.has(lower)) return true;
      if (optionalCrossFileMetrics.has(lower)) return true;
      return false;
    };

    // Derive new features directly from checked rules (not from engineered_columns which is only populated after apply)
    const activeNewFeatures = [];
    llmRules.forEach((rule, idx) => {
      const ruleId = rule.rule_id || `feat_${idx}`;
      if (selectedRuleIds.has(ruleId)) {
        const featName = getRuleFeatureName(rule);
        if (featName) activeNewFeatures.push(featName);
      }
    });
    // Also include stat action features if checked
    const statActions = currentResult.statistical_validation?.action_proposals || [];
    statActions.forEach((action) => {
      if (selectedRuleIds.has(action.action_id) && action.target_column) {
        activeNewFeatures.push(`${action.target_column} (${action.action_type})`);
      }
    });

    const summary = {
      numerical: [],
      categorical: [],
      timestamp: [],
      identifiers: [],
      new_features: activeNewFeatures,
      role_map: {
        actor_id: [],
        object_id: [],
        interaction_value: [],
        timestamp: [],
        demographic_attribute: [],
        item_metadata: []
      }
    };

    const isTemporalName = (colName) => {
      const lower = colName.toLowerCase();
      return (
        /(date|time|timestamp|created|updated|purchased|year|month|day|weekend|hour|_dt)$/i.test(colName) ||
        lower.includes("_is_weekend") ||
        lower.includes("_month") ||
        lower.includes("_year") ||
        lower.includes("_day")
      );
    };

    for (const [col, info] of Object.entries(currentResult.enriched_data_dictionary.columns)) {
      if (isExcluded(col)) continue;

      const type = info.column_type;
      const entity = info.entity_type;
      const colLower = col.toLowerCase();

      if (type === "identifier") summary.identifiers.push(col);
      else if (type === "timestamp" || isTemporalName(col)) summary.timestamp.push(col);
      else if (type === "categorical" || type === "text") summary.categorical.push(col);
      else summary.numerical.push(col);

      if (type === "identifier") {
        if (entity === "user" || colLower.includes("user") || colLower.includes("cust")) {
          summary.role_map.actor_id.push(col);
        } else {
          summary.role_map.object_id.push(col);
        }
      } else if (type === "timestamp" || isTemporalName(col)) {
        summary.role_map.timestamp.push(col);
      } else if (
        colLower.includes("spend") ||
        colLower.includes("price") ||
        colLower.includes("amount") ||
        colLower.includes("revenue") ||
        colLower.includes("count") ||
        colLower.includes("rating") ||
        colLower.includes("qty") ||
        colLower.includes("units") ||
        colLower.includes("score") ||
        colLower.includes("val") ||
        type === "target"
      ) {
        summary.role_map.interaction_value.push(col);
      } else if (entity === "user" || colLower.includes("age") || colLower.includes("gender") || colLower.includes("tenure")) {
        summary.role_map.demographic_attribute.push(col);
      } else {
        summary.role_map.item_metadata.push(col);
      }
    }
    return summary;
  };

  const featureStats = getFeatureSummaryStats();

  return (
    <div className="min-h-screen text-slate-900 bg-slate-50/50">
      <header className="border-b border-sky-100/80 bg-white/70 backdrop-blur px-6 py-4 flex items-center justify-between shadow-sm">
        <div>
          <h1 className="text-lg font-semibold">Automated Data Cleansing, Feature Engineering & Validation Pipeline</h1>
          <p className="text-xs text-slate-400">
            Review, customize & approve cleansing rules, AI-generated features and statistical actions before EDA.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowDictPanel(!showDictPanel)}
            className="rounded-md border border-sky-300 bg-sky-50 hover:bg-sky-100 text-sky-800 px-3 py-1.5 text-xs font-semibold shadow-sm transition"
          >
            {showDictPanel ? "Close Data Dictionary" : "Upload / Edit Data Dictionary"}
          </button>
          <code className="text-xs text-slate-400">{runId}</code>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8 space-y-8">
        {statusError && <p className="text-sm text-rose-600">{statusError}</p>}
        {error && <p className="text-sm text-rose-600">Request Error: {error}</p>}
        {applySuccess && (
          <div className="rounded-md border border-emerald-200 bg-emerald-50 p-4 text-xs text-emerald-800 shadow-sm flex items-center justify-between">
            <span>{applySuccess}</span>
            <span className="font-semibold">
              {!isLastFile ? `Moving to ${nextFileName?.toUpperCase()}.CSV next...` : "Navigating to EDA..."}
            </span>
          </div>
        )}

        {/* DATA DICTIONARY INPUT PANEL */}
        {showDictPanel && (
          <div className="rounded-md border border-sky-200 bg-white p-5 shadow-md space-y-3">
            <h3 className="text-sm font-semibold text-slate-800">
              Data Dictionary Input (Optional Context for LLM & Categorization)
            </h3>
            <p className="text-xs text-slate-500">
              Paste JSON or key=value descriptions below (e.g. <code className="bg-slate-100 px-1 py-0.5 rounded">{"{\"price\": \"Unit price in INR\"}"}</code>):
            </p>
            <textarea
              value={dictInputText}
              onChange={(e) => setDictInputText(e.target.value)}
              rows={4}
              placeholder={`{\n  "unit_price": "Unit selling price of retail item",\n  "customer_id": "Unique customer account ID"\n}`}
              className="w-full font-mono text-xs p-3 rounded border border-slate-300 focus:outline-none focus:ring-1 focus:ring-sky-500"
            />
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowDictPanel(false)} className="px-3 py-1.5 text-xs text-slate-600 hover:text-slate-800">
                Cancel
              </button>
              <button onClick={handleSaveDataDictionary} className="rounded bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold px-4 py-1.5 shadow-sm">
                Enrich & Re-classify
              </button>
            </div>
          </div>
        )}

        {/* File Switcher Tabs */}
        {fileList.length > 0 && (
          <div className="flex items-center gap-2 border-b border-sky-100 pb-3">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider mr-2">Uploaded Files:</span>
            {fileList.map((dsName, idx) => (
              <button
                key={dsName}
                onClick={() => {
                  setActiveDataset(dsName);
                  setApplySuccess(null);
                }}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition ${activeDataset === dsName
                    ? "bg-sky-100 text-sky-800 border border-sky-200 shadow-sm"
                    : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-50"
                  }`}
              >
                Step {idx + 1}: {dsName.toUpperCase()}.CSV
              </button>
            ))}
          </div>
        )}

        {/* Loading State */}
        {loading && (
          <div className="rounded-md border border-sky-100 bg-white/80 p-8 text-center space-y-3 shadow-sm">
            <p className="text-sm font-medium text-slate-700">Analyzing schema & preparing {datasetNameUpper}.CSV...</p>
          </div>
        )}

        {/* Main Dashboard */}
        {!loading && currentResult && (
          <>
            {/* Rule Counter Summary Bar */}
            <div className="rounded-md border border-sky-200 bg-sky-50/60 p-3 shadow-sm flex items-center justify-between text-xs text-slate-700">
              <div>
                <span>Total Active Rules: </span>
                <strong className="text-sky-800 text-sm ml-1">{totalApprovedCount} Rules</strong>
                <span className="text-slate-500 ml-2">({baselineCount} System Cleanups + {tickedCount} Selected Rules)</span>
              </div>
              <span className="text-slate-500">File Shape: {currentResult.refined_shape?.rows || 0} rows × {currentResult.refined_shape?.cols || 0} cols</span>
            </div>

            {/* STAGE 1: Standard System Cleanups */}
            <section className="space-y-3">
              <h2 className="text-sm font-semibold text-slate-800 uppercase tracking-wider">
                1. Standard Data Cleanups & System Rules
              </h2>
              <div className="rounded-md border border-sky-100 bg-white p-4 shadow-sm space-y-2">
                {baselineRules.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {baselineRules.map((ruleStr, idx) => (
                      <span key={idx} className="bg-sky-50 text-sky-700 border border-sky-200 text-xs px-2.5 py-1 rounded font-mono">
                        {formatUserFriendlyRule(ruleStr)}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-400 italic">No standard cleanups required for this file.</p>
                )}
              </div>
            </section>

            {/* STAGE 2: AI-Recommended Features */}
            <section className="space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-slate-800 uppercase tracking-wider">
                  2. AI-Recommended New Features (Check box to approve & edit)
                </h2>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => toggleAllRules(true)}
                    className="text-xs font-semibold text-sky-700 bg-sky-50 border border-sky-200 px-2 py-0.5 rounded hover:bg-sky-100 transition"
                  >
                    Select All
                  </button>
                  <button
                    type="button"
                    onClick={() => toggleAllRules(false)}
                    className="text-xs font-semibold text-slate-600 bg-slate-100 border border-slate-200 px-2 py-0.5 rounded hover:bg-slate-200 transition"
                  >
                    Deselect All
                  </button>
                </div>
              </div>
              <div className="space-y-4">
                {currentResult.llm_recommendations?.feature_engineering_rules?.length > 0 ? (
                  currentResult.llm_recommendations.feature_engineering_rules.map((rule, idx) => {
                    const ruleId = rule.rule_id || `feat_${idx}`;
                    const isChecked = selectedRuleIds.has(ruleId);
                    const code = customCodeMap[ruleId] !== undefined ? customCodeMap[ruleId] : rule.code_snippet;

                    return (
                      <div key={ruleId} className={`rounded-md border p-4 transition shadow-sm bg-white ${isChecked ? "border-sky-300 ring-1 ring-sky-200" : "border-slate-200 opacity-75"}`}>
                        <div className="flex items-center justify-between">
                          <label className="flex items-center gap-2.5 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={() => toggleRule(ruleId)}
                              className="w-4 h-4 rounded border-slate-300 text-sky-600 focus:ring-sky-500"
                            />
                            <span className="text-sm font-semibold text-slate-800">{rule.feature_name || `Feature ${idx + 1}`}</span>
                            <span className="text-xs px-2 py-0.5 rounded bg-purple-50 text-purple-700 border border-purple-200">
                              {rule.feature_type || "Feature"}
                            </span>
                          </label>
                          <span className="text-xs text-slate-500 italic">{rule.rationale}</span>
                        </div>

                        {isChecked && (
                          <div className="mt-3 pt-3 border-t border-slate-100">
                            <label className="block text-[11px] font-semibold text-slate-400 mb-1 uppercase tracking-wider">
                              Python Formula (Human Editable):
                            </label>
                            <textarea
                              value={code}
                              onChange={(e) => handleCodeChange(ruleId, e.target.value)}
                              rows={2}
                              className="w-full bg-slate-900 text-emerald-400 font-mono text-xs p-2.5 rounded border border-slate-700 focus:outline-none focus:ring-1 focus:ring-sky-500"
                            />
                          </div>
                        )}
                      </div>
                    );
                  })
                ) : (
                  <div className="p-4 bg-white rounded border border-slate-200 text-xs text-slate-400 italic">
                    No additional feature engineering rules recommended for this file.
                  </div>
                )}
              </div>
            </section>

            {/* STAGE 3: STATISTICAL VALIDATION & REFINEMENT ACTIONS (NEW SECTION) */}
            <section className="space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-slate-800 uppercase tracking-wider">
                  3. Statistical Validation & Refinement Actions (Check box to approve action)
                </h2>
                <span className="text-xs text-slate-400">Select box to approve refinement action</span>
              </div>
              <div className="space-y-3">
                {currentResult.statistical_validation?.action_proposals?.length > 0 ? (
                  currentResult.statistical_validation.action_proposals.map((action) => {
                    const actionId = action.action_id;
                    const isChecked = selectedRuleIds.has(actionId);

                    return (
                      <div key={actionId} className={`rounded-md border p-3.5 transition shadow-sm bg-white ${isChecked ? "border-amber-300 ring-1 ring-amber-200" : "border-slate-200 opacity-80"}`}>
                        <div className="flex items-center justify-between">
                          <label className="flex items-center gap-2.5 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={() => toggleRule(actionId)}
                              className="w-4 h-4 rounded border-slate-300 text-amber-600 focus:ring-amber-500"
                            />
                            <span className="text-xs font-semibold text-slate-800 uppercase tracking-wider">
                              Action: {action.action_type.replace("_", " ")} on '{action.target_column}'
                            </span>
                            <span className={`text-[10px] px-2 py-0.5 rounded uppercase font-bold ${action.severity === "high" ? "bg-rose-50 text-rose-700 border border-rose-200" : action.severity === "medium" ? "bg-amber-50 text-amber-700 border border-amber-200" : "bg-sky-50 text-sky-700 border border-sky-200"}`}>
                              {action.severity} Priority
                            </span>
                          </label>
                        </div>
                        <p className="text-xs text-slate-600 mt-1.5 ml-6 italic">{action.reason}</p>
                      </div>
                    );
                  })
                ) : (
                  <div className="p-3.5 bg-emerald-50/60 rounded border border-emerald-200 text-xs text-emerald-800">
                    <strong>Statistical Validation Passed:</strong> No zero-variance, high multicollinearity, or extreme outlier actions required.
                  </div>
                )}
              </div>
            </section>

            {/* STAGE 4: FEATURE SUMMARY PANELS */}
            {featureStats && (
              <section className="space-y-4">
                <h2 className="text-sm font-semibold text-slate-800 uppercase tracking-wider">
                  4. Feature Analysis & Category Summary ({datasetNameUpper}.CSV)
                </h2>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* PANEL 1: Newly Added Features List */}
                  <div className="rounded-md border border-purple-200 bg-purple-50/40 p-4 shadow-sm space-y-2">
                    <span className="text-xs font-semibold text-purple-900 uppercase tracking-wider block">
                      Newly Added Features List ({featureStats.new_features.length})
                    </span>
                    {featureStats.new_features.length > 0 ? (
                      <div className="flex flex-wrap gap-1.5 font-mono">
                        {featureStats.new_features.map((feat) => (
                          <span key={feat} className="bg-purple-100 text-purple-800 text-[11px] px-2 py-0.5 rounded font-semibold border border-purple-200">
                            + {feat}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-slate-400 italic">Select feature checkboxes above to enable new features.</p>
                    )}
                  </div>

                  {/* PANEL 2: Data Types Breakdown */}
                  <div className="rounded-md border border-sky-200 bg-sky-50/40 p-4 shadow-sm space-y-2">
                    <span className="text-xs font-semibold text-sky-900 uppercase tracking-wider block">
                      Data Types Breakdown
                    </span>
                    <div className="text-xs space-y-1 text-slate-700">
                      <div><strong>Numerical ({featureStats.numerical.length}):</strong> {featureStats.numerical.join(", ") || "None"}</div>
                      <div><strong>Categorical ({featureStats.categorical.length}):</strong> {featureStats.categorical.join(", ") || "None"}</div>
                      <div><strong>Timestamps ({featureStats.timestamp.length}):</strong> {featureStats.timestamp.join(", ") || "None"}</div>
                      <div><strong>Identifiers ({featureStats.identifiers.length}):</strong> {featureStats.identifiers.join(", ") || "None"}</div>
                    </div>
                  </div>
                </div>

                {/* PANEL 3: Categories Mapping */}
                <div className="rounded-md border border-slate-200 bg-white p-4 shadow-sm space-y-3">
                  <span className="text-xs font-semibold text-slate-700 uppercase tracking-wider block">
                    Feature Categories Mapping:
                  </span>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                    <div className="text-xs bg-slate-50 p-2.5 rounded border border-slate-200">
                      <span className="font-semibold text-blue-700">User Actor Keys:</span>
                      <div className="font-mono text-[11px] text-slate-600 mt-1">{featureStats.role_map.actor_id.join(", ") || "None"}</div>
                    </div>
                    <div className="text-xs bg-slate-50 p-2.5 rounded border border-slate-200">
                      <span className="font-semibold text-purple-700">Item Object Keys:</span>
                      <div className="font-mono text-[11px] text-slate-600 mt-1">{featureStats.role_map.object_id.join(", ") || "None"}</div>
                    </div>
                    <div className="text-xs bg-slate-50 p-2.5 rounded border border-slate-200">
                      <span className="font-semibold text-emerald-700">Interaction Measures:</span>
                      <div className="font-mono text-[11px] text-slate-600 mt-1">{featureStats.role_map.interaction_value.join(", ") || "None"}</div>
                    </div>
                    <div className="text-xs bg-slate-50 p-2.5 rounded border border-slate-200">
                      <span className="font-semibold text-amber-700">Temporal Features:</span>
                      <div className="font-mono text-[11px] text-slate-600 mt-1">{featureStats.role_map.timestamp.join(", ") || "None"}</div>
                    </div>
                    <div className="text-xs bg-slate-50 p-2.5 rounded border border-slate-200">
                      <span className="font-semibold text-pink-700">Actor Demographics:</span>
                      <div className="font-mono text-[11px] text-slate-600 mt-1">{featureStats.role_map.demographic_attribute.join(", ") || "None"}</div>
                    </div>
                    <div className="text-xs bg-slate-50 p-2.5 rounded border border-slate-200">
                      <span className="font-semibold text-indigo-700">Item Metadata Context:</span>
                      <div className="font-mono text-[11px] text-slate-600 mt-1">{featureStats.role_map.item_metadata.join(", ") || "None"}</div>
                    </div>
                  </div>
                </div>
              </section>
            )}

            {/* STAGE 5: Preview Data Table */}
            {currentResult.preview_data && currentResult.preview_data.length > 0 && (
              <section className="space-y-3">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-semibold text-slate-800 uppercase tracking-wider">
                    5. Preview Updated Data Table ({datasetNameUpper}.CSV)
                  </h2>
                  <span className="text-xs text-slate-500">
                    Showing top 10 rows of {currentResult.refined_shape?.cols || 0} columns
                  </span>
                </div>
                <div className="rounded-md border border-sky-100 bg-white p-4 shadow-sm overflow-x-auto">
                  <table className="w-full text-left text-xs text-slate-700">
                    <thead className="bg-sky-50/70 text-slate-600 uppercase border-b border-sky-100">
                      <tr>
                        {Object.keys(currentResult.preview_data[0]).map((col) => {
                          const isNew = currentResult.engineered_columns?.includes(col);
                          return (
                            <th key={col} className={`p-2.5 whitespace-nowrap ${isNew ? "text-purple-700 font-bold bg-purple-50" : ""}`}>
                              {col} {isNew && "(New)"}
                            </th>
                          );
                        })}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 font-mono">
                      {currentResult.preview_data.slice(0, 10).map((row, idx) => (
                        <tr key={idx} className="hover:bg-sky-50/30">
                          {Object.entries(row).map(([col, val]) => {
                            const isNew = currentResult.engineered_columns?.includes(col);
                            return (
                              <td key={col} className={`p-2.5 whitespace-nowrap ${isNew ? "bg-purple-50/50 text-purple-800 font-medium" : ""}`}>
                                {String(val)}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {/* Action Card */}
            <div className="rounded-md border border-sky-200 bg-white p-4 shadow-sm flex items-center justify-between gap-4">
              <div>
                <p className="text-sm font-semibold text-slate-800">
                  {!isLastFile
                    ? `Save ${activeDataset.toUpperCase()}.CSV and move to ${nextFileName?.toUpperCase()}.CSV?`
                    : "Save final file and proceed to Data Review (EDA)?"}
                </p>
                <p className="text-xs text-slate-500">Applies all {totalApprovedCount} active rules & actions to disk.</p>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={handleApplyRules}
                  disabled={applying}
                  className="rounded-md bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 text-sm font-medium shadow-sm transition"
                >
                  {applying
                    ? "Saving & Updating..."
                    : !isLastFile
                      ? `Apply ${totalApprovedCount} Rules & Next File »`
                      : `Apply ${totalApprovedCount} Rules & Finish »`}
                </button>
                <button
                  onClick={() => navigate(`/eda/${runId}`)}
                  className="rounded-md bg-sky-600 hover:bg-sky-500 text-white px-4 py-2 text-sm font-medium shadow-sm"
                >
                  Skip to EDA »
                </button>
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
