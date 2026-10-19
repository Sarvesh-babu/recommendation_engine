import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getModelOptions, startTraining } from "../api";

const CATEGORY_LABELS = {
  personalized: "Personalized",
  fbt: "Frequently bought together",
  popular: "Popular",
};

export default function ModelSettingsPage() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const [options, setOptions] = useState(null);
  const [selected, setSelected] = useState({});
  const [error, setError] = useState(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    getModelOptions()
      .then((data) => {
        setOptions(data);
        const defaults = {};
        for (const category of Object.keys(data)) {
          defaults[category] = data[category].find((o) => o.default)?.name ?? data[category][0]?.name;
        }
        setSelected(defaults);
      })
      .catch((err) => setError(err.message));
  }, []);

  async function handleStart() {
    setStarting(true);
    setError(null);
    try {
      await startTraining(runId, selected);
      navigate(`/results/${runId}`);
    } catch (err) {
      setError(err.message);
      setStarting(false);
    }
  }

  return (
    <div className="min-h-screen text-slate-900">
      <header className="border-b border-slate-200 bg-white px-6 py-4 shadow-sm">
        <h1 className="text-lg font-bold text-slate-900">Model settings</h1>
        <p className="text-xs text-slate-500">
          Configure model algorithms and re-train at any time without re-uploading datasets or repeating EDA.
        </p>
      </header>

      <main className="max-w-2xl mx-auto px-6 py-8 space-y-6">
        {error && <p className="text-sm text-rose-600 font-medium">{error}</p>}
        {!options && !error && <p className="text-sm text-slate-500">Loading model options...</p>}

        {options &&
          Object.entries(options).map(([category, opts]) => (
            <fieldset key={category} className="space-y-2">
              <legend className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-2">{CATEGORY_LABELS[category]}</legend>
              <div className="space-y-2">
                {opts.map((opt) => (
                  <label
                    key={opt.name}
                    className={`flex items-start gap-3 rounded-lg border px-3.5 py-2.5 shadow-sm cursor-pointer transition ${
                      selected[category] === opt.name
                        ? "border-sky-500 bg-sky-50/60"
                        : "border-slate-200 bg-white hover:bg-slate-50"
                    }`}
                  >
                    <input
                      type="radio"
                      name={category}
                      value={opt.name}
                      checked={selected[category] === opt.name}
                      onChange={() => setSelected((prev) => ({ ...prev, [category]: opt.name }))}
                      className="mt-1"
                    />
                    <div>
                      <p className="text-sm font-semibold text-slate-800">{opt.label}</p>
                      <p className="text-xs text-slate-500">{opt.description}</p>
                    </div>
                  </label>
                ))}
              </div>
            </fieldset>
          ))}

        {options && (
          <button
            onClick={handleStart}
            disabled={starting}
            className="w-full rounded-lg bg-sky-800 hover:bg-sky-900 text-white disabled:opacity-40 disabled:cursor-not-allowed px-4 py-2.5 text-sm font-semibold transition shadow-sm"
          >
            {starting ? "Training models..." : "Run / Re-train Models"}
          </button>
        )}
      </main>
    </div>
  );
}
