/* Shared building blocks for the Insights layer. */

export function SectionHeader({ title, subtitle, children }) {
  return (
    <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h2 className="text-sm font-bold uppercase tracking-wider text-slate-800">{title}</h2>
        {subtitle && <p className="text-xs text-slate-500 mt-0.5 max-w-3xl">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}

export function StatCard({ label, value, sub }) {
  return (
    <div className="bg-white border border-slate-200 rounded-lg px-4 py-3 flex flex-col gap-0.5 min-w-[9rem]">
      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{label}</span>
      <span className="text-lg font-bold text-slate-900">{value}</span>
      {sub && <span className="text-[10px] text-slate-500">{sub}</span>}
    </div>
  );
}

const BADGE = {
  sky: "bg-sky-100 text-sky-800 border-sky-200",
  emerald: "bg-emerald-100 text-emerald-800 border-emerald-200",
  amber: "bg-amber-100 text-amber-800 border-amber-200",
  rose: "bg-rose-100 text-rose-800 border-rose-200",
  violet: "bg-violet-100 text-violet-800 border-violet-200",
  slate: "bg-slate-100 text-slate-700 border-slate-200",
};

export function Badge({ children, variant = "slate" }) {
  return (
    <span className={`${BADGE[variant] || BADGE.slate} border text-[9px] font-bold px-2 py-0.5 rounded uppercase tracking-wide whitespace-nowrap`}>
      {children}
    </span>
  );
}

/** The formula behind a module, shown so every number is auditable. */
export function Formula({ children }) {
  return (
    <details className="mt-4 rounded-lg border border-slate-200 bg-slate-50 px-4 py-2 text-[11px] text-slate-600">
      <summary className="cursor-pointer font-semibold text-slate-700">How this is calculated</summary>
      <div className="mt-2 space-y-1 font-mono leading-relaxed">{children}</div>
    </details>
  );
}

export function ModuleError({ data }) {
  if (!data?.error) return null;
  return <p className="text-xs text-slate-500 italic">{data.error}</p>;
}

export function Empty({ children }) {
  return <p className="text-xs text-slate-500 italic py-4">{children}</p>;
}

export function Th({ children, right }) {
  return <th className={`py-2 px-2 font-bold whitespace-nowrap ${right ? "text-right" : "text-left"}`}>{children}</th>;
}

export function Td({ children, right, strong, className = "" }) {
  return (
    <td className={`py-2 px-2 ${right ? "text-right tabular-nums" : ""} ${strong ? "font-semibold text-slate-900" : "text-slate-700"} ${className}`}>
      {children}
    </td>
  );
}

export function Table({ head, children }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="w-full text-[11px]">
        <thead>
          <tr className="bg-slate-800 text-white">{head}</tr>
        </thead>
        <tbody className="divide-y divide-slate-100 bg-white">{children}</tbody>
      </table>
    </div>
  );
}

export function ChartTooltip({ active, payload, label, render }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-slate-200 bg-white px-3 py-2 text-[11px] shadow-lg text-slate-700">
      {render ? render(payload[0].payload, label) : null}
    </div>
  );
}
