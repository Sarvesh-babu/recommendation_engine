import { useState } from "react";
import { Formula, ModuleError, SectionHeader, StatCard } from "./ui";
import { fmtNum, fmtP } from "./format";

const MID = [240, 239, 236]; // neutral grey at lift = 1
const POS = [24, 79, 149]; // blue pole: buys together more than chance
const NEG = [176, 46, 46]; // red pole: buys together less than chance
const SEQ_LO = [205, 226, 251];
const SEQ_HI = [13, 54, 107];

const mix = (a, b, t) => `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * t)).join(",")})`;

/** Diverging on log2(lift), symmetric so 2x and 0.5x are equally intense; clamped at 4x / 0.25x. */
function liftColor(lift) {
  const t = Math.max(-1, Math.min(1, Math.log2(Math.max(lift, 1e-6)) / 2));
  return { bg: t >= 0 ? mix(MID, POS, t) : mix(MID, NEG, -t), dark: Math.abs(t) > 0.55 };
}

function confColor(pct, max) {
  const t = max > 0 ? pct / max : 0;
  return { bg: mix(SEQ_LO, SEQ_HI, t), dark: t > 0.55 };
}

export default function CategoryHeatmap({ data }) {
  const [measure, setMeasure] = useState("lift");
  const [hover, setHover] = useState(null);
  if (data?.error) return <ModuleError data={data} />;

  const cats = data.categories;
  const cell = {};
  data.cells.forEach((c) => (cell[`${c.row}|${c.col}`] = c));
  const maxConf = Math.max(...data.cells.map((c) => c.confidence_pct ?? 0));
  const focus = hover ? cell[hover] : null;

  return (
    <div>
      <SectionHeader
        title="Category Cross-Sell Heatmap"
        subtitle="How strongly each category pulls shoppers into another. Lift shows the pull against chance (1.0x = independent); confidence shows the share of row-category baskets that also contain the column category."
      >
        <div className="flex rounded-md border border-slate-200 bg-white p-0.5 text-xs">
          {[["lift", "Lift"], ["confidence", "Confidence P(col | row)"]].map(([k, label]) => (
            <button
              key={k}
              onClick={() => setMeasure(k)}
              className={`px-3 py-1 rounded ${measure === k ? "bg-slate-800 text-white" : "text-slate-600 hover:bg-slate-100"}`}
            >
              {label}
            </button>
          ))}
        </div>
      </SectionHeader>

      <div className="flex flex-wrap gap-3 mb-4">
        <StatCard label="Baskets analysed" value={fmtNum(data.total_baskets)} sub="with ≥1 categorised item" />
        <StatCard label="Multi-category baskets" value={fmtNum(data.multi_category_baskets)}
          sub={`${((data.multi_category_baskets / data.total_baskets) * 100).toFixed(1)}% of baskets`} />
        <StatCard label="Significant affinities" value={data.strongest_pairs.length} sub="lift > 1, BH q < 0.05" />
        <StatCard label="Significant avoidances" value={data.weakest_pairs.length} sub="lift < 1, BH q < 0.05" />
      </div>

      <div className="overflow-x-auto">
        <table className="border-separate" style={{ borderSpacing: 2 }}>
          <thead>
            <tr>
              <th className="p-2 text-left text-[10px] text-slate-500 font-semibold">row → col</th>
              {cats.map((c) => (
                <th key={c} className="p-2 text-[11px] font-semibold text-slate-700 capitalize min-w-[5.5rem]">{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {cats.map((row) => (
              <tr key={row}>
                <td className="p-2 text-[11px] font-semibold text-slate-700 capitalize whitespace-nowrap">
                  {row}
                  <span className="ml-1 font-normal text-slate-400">({data.basket_share_pct[row]}%)</span>
                </td>
                {cats.map((col) => {
                  const key = `${row}|${col}`;
                  const c = cell[key];
                  if (row === col) {
                    return <td key={col} className="rounded text-center text-[10px] text-slate-400 bg-slate-50">—</td>;
                  }
                  const { bg, dark } = measure === "lift" ? liftColor(c.lift) : confColor(c.confidence_pct, maxConf);
                  const sig = c.association !== "independent";
                  return (
                    <td
                      key={col}
                      onMouseEnter={() => setHover(key)}
                      onMouseLeave={() => setHover(null)}
                      className={`rounded px-2 py-3 text-center text-[11px] tabular-nums cursor-default transition ${
                        hover === key ? "ring-2 ring-slate-900" : ""
                      } ${c.low_support ? "opacity-60" : ""}`}
                      style={{ background: bg, color: dark ? "#fff" : "#0b0b0b" }}
                    >
                      <span className={sig ? "font-bold" : ""}>
                        {measure === "lift" ? `${c.lift.toFixed(2)}x` : `${c.confidence_pct}%`}
                      </span>
                      {sig && <span aria-label="significant"> ●</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-4 text-[10px] text-slate-500">
        {measure === "lift" ? (
          <span className="flex items-center gap-2">
            <span>0.25x</span>
            <span className="h-2.5 w-40 rounded" style={{ background: `linear-gradient(90deg, rgb(${NEG}), rgb(${MID}), rgb(${POS}))` }} />
            <span>4x</span>
            <span className="ml-1">(1.0x = independent)</span>
          </span>
        ) : (
          <span className="flex items-center gap-2">
            <span>0%</span>
            <span className="h-2.5 w-40 rounded" style={{ background: `linear-gradient(90deg, rgb(${SEQ_LO}), rgb(${SEQ_HI}))` }} />
            <span>{maxConf}%</span>
          </span>
        )}
        <span>● significant (BH q &lt; {data.alpha})</span>
        <span>faded = fewer than {data.min_cell_support} baskets</span>
      </div>

      <div className="mt-3 min-h-[2.5rem] rounded-md bg-slate-50 border border-slate-200 px-3 py-2 text-[11px] text-slate-700">
        {focus ? (
          <>
            <b className="capitalize">{focus.row}</b> → <b className="capitalize">{focus.col}</b>: {focus.count} shared baskets ·
            P({focus.col} | {focus.row}) = {focus.confidence_pct}% · lift {focus.lift.toFixed(3)}x · q = {fmtP(focus.q_value)} ·{" "}
            <span className="font-semibold">{focus.association}</span>
          </>
        ) : (
          <span className="text-slate-400">Hover a cell for counts and significance.</span>
        )}
      </div>

      <Formula>
        <div>n(X) = baskets with category X · n(X,Y) = baskets with both · N = {fmtNum(data.total_baskets)}</div>
        <div>confidence(X→Y) = n(X,Y) / n(X)</div>
        <div>lift(X,Y) = n(X,Y) · N / (n(X) · n(Y))</div>
        <div>significance: two-sided hypergeometric test, Benjamini–Hochberg adjusted across all category pairs</div>
      </Formula>
    </div>
  );
}
