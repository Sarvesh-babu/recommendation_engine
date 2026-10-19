import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getEda } from "../api";
import { usePipelineStatus } from "../hooks/usePipelineStatus";
import EdaCharts from "../components/EdaCharts";

const EDA_AVAILABLE_STATUSES = ["eda_ready", "training", "completed"];

export default function EdaReviewPage() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const { run, error: statusError } = usePipelineStatus(runId);
  const [eda, setEda] = useState(null);
  const [edaError, setEdaError] = useState(null);

  useEffect(() => {
    if (run && EDA_AVAILABLE_STATUSES.includes(run.status)) {
      getEda(runId)
        .then(setEda)
        .catch((err) => setEdaError(err.message));
    }
  }, [run, runId]);

  return (
    <div className="min-h-screen text-slate-900 bg-slate-50/50">
      <header className="border-b border-sky-100/80 bg-white/70 backdrop-blur px-6 py-4 flex items-center justify-between shadow-sm">
        <div>
          <h1 className="text-lg font-semibold">Exploratory Data Analysis (EDA) & Feature Health</h1>
          <p className="text-sm text-slate-500">Review refined feature distributions & dataset stats, then select recommendation models.</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate(`/layer1/${runId}`)}
            className="rounded-md border border-sky-300 bg-sky-50 hover:bg-sky-100 text-sky-800 px-3 py-1.5 text-xs font-semibold shadow-sm transition"
          >
            « Back to Layer 1 Refinement
          </button>
          <code className="text-xs text-slate-400">{runId}</code>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8 space-y-8">
        {statusError && <p className="text-sm text-rose-600">{statusError}</p>}
        {run?.status === "validating" && <p className="text-sm text-slate-500">Validating dataset schema...</p>}
        {run?.status === "failed" && <p className="text-sm text-rose-600">{run.error}</p>}

        {edaError && <p className="text-sm text-rose-600">{edaError}</p>}
        {eda && <EdaCharts eda={eda} />}

        {run?.status === "eda_ready" && eda && (
          <div className="rounded-md border border-sky-200 bg-white p-4 shadow-sm flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-slate-800">Refined Data & Features Verified?</p>
              <p className="text-xs text-slate-500">Proceed to configure personalized recommendation algorithms & model parameters.</p>
            </div>
            <button
              onClick={() => navigate(`/models/${runId}`)}
              className="rounded-md bg-sky-600 hover:bg-sky-500 text-white px-5 py-2.5 text-sm font-medium shadow-sm transition whitespace-nowrap"
            >
              Continue to Model Settings »
            </button>
          </div>
        )}

        {(run?.status === "training" || run?.status === "completed") && (
          <div className="p-4 bg-sky-50 border border-sky-200 rounded text-xs text-sky-800 flex items-center justify-between">
            <span>Training initiated or completed for this pipeline run.</span>
            <button onClick={() => navigate(`/results/${runId}`)} className="font-semibold text-sky-700 underline">
              Go to Results »
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
