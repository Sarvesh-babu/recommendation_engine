import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import UploadForm from "../components/UploadForm";
import { listRuns } from "../api";

const STATUS_TARGET = {
  completed: (runId) => `/results/${runId}`,
  training: (runId) => `/models/${runId}`,
  eda_ready: (runId) => `/eda/${runId}`,
  validating: (runId) => `/eda/${runId}`,
};

const STATUS_LABEL = {
  completed: "Completed",
  training: "Training...",
  eda_ready: "EDA ready",
  validating: "Validating...",
  failed: "Failed",
};

export default function UploadPage() {
  const navigate = useNavigate();
  const [runs, setRuns] = useState([]);
  const [runsError, setRunsError] = useState(null);

  useEffect(() => {
    listRuns()
      .then((d) => setRuns(d.runs))
      .catch((err) => setRunsError(err.message));
  }, []);

  return (
    <div className="min-h-screen text-slate-900">
      <header className="border-b border-sky-100/80 bg-white/70 backdrop-blur px-6 py-4 shadow-sm">
        <h1 className="text-lg font-semibold">Recommendation Accelerator</h1>
        <p className="text-sm text-slate-500">Upload your data to get started.</p>
      </header>

      <main className="max-w-2xl mx-auto px-6 py-10 space-y-8">
        <UploadForm onRunStarted={(runId) => navigate(`/eda/${runId}`)} />

        <div className="space-y-2">
          <h2 className="text-sm font-semibold text-slate-800">Past runs</h2>
          {runsError && <p className="text-sm text-rose-600">{runsError}</p>}
          {!runsError && runs.length === 0 && (
            <p className="text-sm text-slate-500">No previous runs yet -- upload data above to start one.</p>
          )}
          {runs.length > 0 && (
            <ul className="divide-y divide-slate-100 rounded-md border border-sky-100 bg-white/80 shadow-sm">
              {runs.map((run) => {
                const target = STATUS_TARGET[run.status]?.(run.run_id);
                return (
                  <li key={run.run_id} className="flex items-center justify-between px-3 py-2 text-sm">
                    <div>
                      <code className="text-xs text-slate-500">{run.run_id}</code>
                      <span className="ml-2 text-slate-600">{run.industry}</span>
                      <span className="ml-2 text-xs text-slate-400">{run.computed_at}</span>
                      {run.status === "failed" && run.error && (
                        <p className="text-xs text-rose-600 mt-0.5">{run.error}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-3">
                      <span
                        className={`text-xs ${run.status === "failed" ? "text-rose-600" : "text-slate-500"}`}
                      >
                        {STATUS_LABEL[run.status] || run.status}
                      </span>
                      {target && (
                        <button
                          onClick={() => navigate(target)}
                          className="text-xs text-sky-700 hover:text-sky-600 underline"
                        >
                          Open
                        </button>
                      )}
                      {run.status === "completed" && (
                        <button
                          onClick={() => navigate(`/validation/${run.run_id}`)}
                          className="text-xs text-sky-700 hover:text-sky-600 underline"
                        >
                          Validation
                        </button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </main>
    </div>
  );
}
