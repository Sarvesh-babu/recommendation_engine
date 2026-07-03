import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import ganitLogo from "../assets/ganit-logo.png";
import { getModelOptions } from "../api";

const SECTIONS = [
  { key: "personalized", title: "Personalized recommendations", blurb: "Ranked per customer, from their own purchase history." },
  { key: "fbt", title: "Frequently bought together", blurb: "Ranked per product, from basket co-purchase patterns." },
  { key: "popular", title: "Popular / trending", blurb: "Ranked overall or per segment, for customers with no history yet." },
];

export default function HomePage() {
  const navigate = useNavigate();
  const [modelOptions, setModelOptions] = useState(null);

  useEffect(() => {
    getModelOptions().then(setModelOptions).catch(() => setModelOptions(null));
  }, []);

  return (
    <div className="min-h-screen text-slate-900">
      <main className="max-w-4xl mx-auto px-6 py-16 space-y-12">
        <div className="text-center space-y-5">
          <img src={ganitLogo} alt="Ganit" className="h-16 w-auto mx-auto" />
          <h1 className="text-2xl font-semibold">Recommendation Accelerator</h1>
          <p className="text-base text-slate-600 max-w-2xl mx-auto">
            Upload your own transactions, customers, and products, and this app trains and evaluates several
            recommendation approaches over your data -- personalized picks per customer, "frequently bought
            together" pairings per product, and popularity/trending fallbacks -- then lets you explore the
            results, see <em>why</em> each item was recommended, and download an offline evaluation report.
          </p>
          <button
            onClick={() => navigate("/upload")}
            className="rounded-md bg-sky-600 hover:bg-sky-500 px-5 py-2.5 text-sm font-medium text-white shadow-sm"
          >
            Get started
          </button>
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          {SECTIONS.map((section) => (
            <div key={section.key} className="rounded-md border border-sky-100 bg-white/80 p-4 shadow-sm space-y-3">
              <div>
                <h2 className="text-sm font-semibold text-slate-800">{section.title}</h2>
                <p className="text-xs text-slate-500">{section.blurb}</p>
              </div>
              <ul className="space-y-2">
                {(modelOptions?.[section.key] ?? []).map((opt) => (
                  <li key={opt.name} className="text-xs text-slate-600">
                    <span className="font-medium text-slate-800">{opt.label}</span>
                    {opt.default && <span className="ml-1.5 text-sky-600">(default)</span>}
                    <p className="text-slate-500">{opt.description}</p>
                  </li>
                ))}
                {!modelOptions && <li className="text-xs text-slate-400">Loading model options...</li>}
              </ul>
            </div>
          ))}
        </div>

        <div className="rounded-md border border-sky-100 bg-white/80 p-4 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-800 mb-2">What else this covers</h2>
          <ul className="text-sm text-slate-600 space-y-1 list-disc list-inside">
            <li>Pick which algorithm runs for each recommendation type before training, per run.</li>
            <li>EDA and validation checks on your data before committing to a (slower) training step.</li>
            <li>Offline evaluation -- precision/recall/hit-rate@k -- benchmarked against a popularity baseline.</li>
            <li>A plain-language reason attached to every recommendation explaining why it was suggested.</li>
            <li>An Excel export of every result table for sharing outside the app.</li>
          </ul>
        </div>
      </main>
    </div>
  );
}
