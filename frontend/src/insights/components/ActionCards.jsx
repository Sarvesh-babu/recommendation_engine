import { useState } from "react";
import { Badge, Empty, ModuleError, SectionHeader } from "./ui";
import { fmtMoney } from "./format";

const TYPE = {
  cross_sell_campaign: { label: "Cross-sell campaign", variant: "sky" },
  bundle_promotion: { label: "Bundle promotion", variant: "amber" },
  shipping_threshold: { label: "Shipping threshold", variant: "violet" },
  placement: { label: "Placement", variant: "emerald" },
  category_cross_promo: { label: "Category cross-promo", variant: "sky" },
  orphan_product: { label: "Orphan product", variant: "rose" },
  seasonal: { label: "Seasonal", variant: "amber" },
};
const PRIORITY = { high: "rose", medium: "amber", low: "slate" };
const VALUE_KIND = { revenue: "expected revenue", gross_profit: "Δ gross profit", net_contribution: "net contribution" };

const metricLabel = (k) => k.replace(/_/g, " ").replace(/\bpct\b/, "%");

export default function ActionCards({ data }) {
  const [filter, setFilter] = useState("all");
  if (data?.error) return <ModuleError data={data} />;
  const cards = data.cards.filter((c) => filter === "all" || c.priority === filter);

  return (
    <div>
      <SectionHeader
        title="Merchandising Action Cards"
        subtitle="Actions generated from the other five modules. Every figure on a card comes from a computed metric, and the formula is shown on the card."
      >
        <div className="flex rounded-md border border-slate-200 bg-white p-0.5 text-xs">
          {["all", "high", "medium", "low"].map((p) => (
            <button
              key={p}
              onClick={() => setFilter(p)}
              className={`px-3 py-1 rounded capitalize ${filter === p ? "bg-slate-800 text-white" : "text-slate-600 hover:bg-slate-100"}`}
            >
              {p}
            </button>
          ))}
        </div>
      </SectionHeader>

      {cards.length === 0 ? (
        <Empty>No actions at this priority.</Empty>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {cards.map((card, i) => (
            <article key={i} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm flex flex-col gap-2">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge variant={TYPE[card.type]?.variant}>{TYPE[card.type]?.label || card.type}</Badge>
                <Badge variant={PRIORITY[card.priority]}>{card.priority} priority</Badge>
                {card.value_kind && (
                  <span className="ml-auto text-right">
                    <span className="block text-sm font-bold text-slate-900 tabular-nums">{fmtMoney(card.estimated_value)}</span>
                    <span className="block text-[9px] uppercase tracking-wide text-slate-500">{VALUE_KIND[card.value_kind]}</span>
                  </span>
                )}
              </div>
              <h3 className="text-sm font-bold text-slate-900">{card.title}</h3>
              <p className="text-xs text-slate-600 leading-relaxed">{card.description}</p>
              <dl className="mt-auto flex flex-wrap gap-x-4 gap-y-1 pt-2 border-t border-slate-100">
                {Object.entries(card.metrics).map(([k, v]) => (
                  <div key={k} className="text-[10px]">
                    <dt className="inline text-slate-500 capitalize">{metricLabel(k)}: </dt>
                    <dd className="inline font-semibold text-slate-800 tabular-nums">{typeof v === "number" ? v.toLocaleString() : v}</dd>
                  </div>
                ))}
              </dl>
              <p className="text-[10px] font-mono text-slate-400">{card.formula}</p>
            </article>
          ))}
        </div>
      )}
      <p className="mt-3 text-[10px] text-slate-500">
        Card values are different measures (revenue, gross profit, net contribution) and are deliberately not summed.
      </p>
    </div>
  );
}
