import { useEffect, useRef, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { getPromotionOptimizer } from "../insightsApi";
import { Badge, ChartTooltip, Formula, ModuleError, SectionHeader, StatCard, Table, Td, Th } from "./ui";
import { INK, SERIES, fmtMoney } from "./format";

const NEG = "#e34948";

const FIELDS = [
  { key: "nudge_window", label: "Nudge window", hint: "carts within this share of the threshold can be nudged", min: 0.5, max: 0.95, step: 0.05, pct: true },
  { key: "nudge_conversion", label: "Nudge conversion", hint: "share of nudgeable carts that top up", min: 0, max: 1, step: 0.05, pct: true },
  { key: "shipping_cost", label: "Shipping cost / order", hint: "cost absorbed per free-shipped order", min: 0, max: 50, step: 0.5 },
  { key: "gross_margin", label: "Gross margin", hint: "margin on merchandise", min: 0.05, max: 0.9, step: 0.05, pct: true },
  { key: "discount_elasticity", label: "Discount elasticity", hint: "relative attach-rate gain per unit of discount", min: 0, max: 10, step: 0.5 },
];

export default function PromotionOptimizer({ data: initial, runId }) {
  const [data, setData] = useState(initial);
  const [assumptions, setAssumptions] = useState(initial?.assumptions);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const first = useRef(true);

  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    const t = setTimeout(() => {
      setLoading(true);
      getPromotionOptimizer(runId, assumptions)
        .then((d) => { setData(d); setError(null); })
        .catch((e) => setError(e.message))
        .finally(() => setLoading(false));
    }, 350);
    return () => clearTimeout(t);
  }, [assumptions, runId]);

  if (initial?.error) return <ModuleError data={initial} />;

  const bs = data.basket_stats;
  const rec = data.shipping_scenarios.find((s) => s.threshold === data.recommended_threshold);
  const bestBundle = data.bundle_scenarios.find((s) => s.discount_pct === data.recommended_discount_pct);

  return (
    <div className={loading ? "opacity-60 transition" : "transition"}>
      <SectionHeader
        title="Promotion & Threshold Optimizer"
        subtitle="Simulates free-shipping thresholds and bundle discounts against the no-promotion baseline on your historical baskets. Behavioural inputs can't be learned from baskets alone, so they are editable assumptions."
      />

      <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 mb-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600">Assumptions</h3>
          <button className="text-[11px] text-sky-700 hover:underline" onClick={() => setAssumptions(initial.assumptions)}>
            Reset defaults
          </button>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {FIELDS.map((f) => (
            <label key={f.key} className="text-[11px] text-slate-700">
              <span className="flex justify-between font-semibold">
                {f.label}
                <span className="tabular-nums">{f.pct ? `${Math.round(assumptions[f.key] * 100)}%` : assumptions[f.key]}</span>
              </span>
              <input
                type="range" min={f.min} max={f.max} step={f.step} value={assumptions[f.key]}
                onChange={(e) => setAssumptions((a) => ({ ...a, [f.key]: Number(e.target.value) }))}
                className="w-full accent-slate-800"
              />
              <span className="text-[10px] text-slate-500">{f.hint}</span>
            </label>
          ))}
        </div>
        {error && <p className="mt-2 text-xs text-rose-700">{error}</p>}
      </div>

      <div className="flex flex-wrap gap-3 mb-5">
        <StatCard label="Avg basket" value={fmtMoney(bs.avg_basket_value, 2)} sub={`median ${fmtMoney(bs.median_basket_value, 2)}`} />
        <StatCard label="Interquartile range" value={`${fmtMoney(bs.p25_basket_value)}–${fmtMoney(bs.p75_basket_value)}`} sub={`${bs.total_baskets} baskets`} />
        <StatCard
          label="Best shipping threshold"
          value={rec ? fmtMoney(rec.threshold) : "—"}
          sub={data.free_shipping_profitable ? `net +${fmtMoney(rec.net_contribution)}` : "no threshold pays back"}
        />
        <StatCard
          label="Best bundle discount"
          value={bestBundle ? `${bestBundle.discount_pct}%` : "None"}
          sub={bestBundle ? `Δ gross profit ${fmtMoney(bestBundle.delta_gross_profit)}` : "every level loses gross profit"}
        />
      </div>

      {/* A. Free shipping */}
      <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-2">A · Free-shipping threshold</h3>
      <div className="grid gap-5 lg:grid-cols-2 mb-4">
        <div>
          <p className="text-[11px] text-slate-500 mb-1">Basket value distribution, with the recommended threshold</p>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.basket_value_histogram} margin={{ left: 0, right: 8, top: 8 }} barCategoryGap={2}>
                <CartesianGrid vertical={false} stroke={INK.grid} />
                <XAxis dataKey="from" type="number" domain={["dataMin", "dataMax"]} tickFormatter={(v) => fmtMoney(v)}
                  tick={{ fontSize: 10, fill: INK.muted }} stroke={INK.axis} />
                <YAxis tick={{ fontSize: 10, fill: INK.muted }} stroke={INK.axis} width={32} />
                <Tooltip
                  cursor={{ fill: "rgba(11,11,11,0.04)" }}
                  content={<ChartTooltip render={(b) => <>{fmtMoney(b.from)}–{fmtMoney(b.to)}: <b>{b.count}</b> baskets</>} />}
                />
                <Bar dataKey="count" fill={SERIES[0]} radius={[4, 4, 0, 0]} />
                {rec && (
                  <ReferenceLine x={rec.threshold} stroke={INK.primary} strokeDasharray="4 3"
                    label={{ value: `T = ${fmtMoney(rec.threshold)}`, fontSize: 10, fill: INK.primary, position: "insideTopRight" }} />
                )}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div>
          <p className="text-[11px] text-slate-500 mb-1">Net contribution by threshold (uplift × margin − shipping subsidy)</p>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.shipping_scenarios} margin={{ left: 8, right: 8, top: 8 }}>
                <CartesianGrid vertical={false} stroke={INK.grid} />
                <XAxis dataKey="threshold" tickFormatter={(v) => fmtMoney(v)} tick={{ fontSize: 10, fill: INK.muted }} stroke={INK.axis} />
                <YAxis tickFormatter={(v) => fmtMoney(v)} tick={{ fontSize: 10, fill: INK.muted }} stroke={INK.axis} width={56} />
                <ReferenceLine y={0} stroke={INK.secondary} />
                <Tooltip
                  cursor={{ fill: "rgba(11,11,11,0.04)" }}
                  content={
                    <ChartTooltip
                      render={(s) => (
                        <>
                          <div className="font-semibold text-slate-900">Threshold {fmtMoney(s.threshold)}</div>
                          <div>uplift {fmtMoney(s.expected_uplift_revenue)} × margin − subsidy {fmtMoney(s.shipping_subsidy)}</div>
                          <div className="font-semibold">net {fmtMoney(s.net_contribution)}</div>
                        </>
                      )}
                    />
                  }
                />
                <Bar dataKey="net_contribution" radius={4}>
                  {data.shipping_scenarios.map((s) => (
                    <Cell key={s.threshold} fill={s.net_contribution >= 0 ? SERIES[0] : NEG} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="text-[10px] text-slate-500">Blue = gains, red = loses money against no free shipping.</p>
        </div>
      </div>

      <Table
        head={
          <>
            <Th right>Threshold</Th><Th right>Qualify now</Th><Th right>Nudgeable</Th><Th right>Avg nudge gap</Th>
            <Th right>Exp. conversions</Th><Th right>Uplift revenue</Th><Th right>Subsidy</Th><Th right>Net contribution</Th>
          </>
        }
      >
        {data.shipping_scenarios.map((s) => (
          <tr key={s.threshold} className={s.threshold === data.recommended_threshold ? "bg-sky-50" : "hover:bg-slate-50"}>
            <Td right strong>{fmtMoney(s.threshold)}</Td>
            <Td right>{s.qualifying_pct}%</Td>
            <Td right>{s.nudgeable_carts}</Td>
            <Td right>{fmtMoney(s.avg_nudge_gap, 2)}</Td>
            <Td right>{s.expected_conversions}</Td>
            <Td right>{fmtMoney(s.expected_uplift_revenue, 2)}</Td>
            <Td right>{fmtMoney(s.shipping_subsidy, 2)}</Td>
            <Td right strong className={s.net_contribution < 0 ? "!text-rose-700" : ""}>{fmtMoney(s.net_contribution, 2)}</Td>
          </tr>
        ))}
      </Table>

      {/* B. Bundles */}
      <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 mt-6 mb-2">B · Bundle discount (top significant pairs)</h3>
      <div className="h-60 mb-4">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data.bundle_scenarios} margin={{ left: 8, right: 8, top: 8 }} barGap={2}>
            <CartesianGrid vertical={false} stroke={INK.grid} />
            <XAxis dataKey="discount_pct" tickFormatter={(v) => `${v}% off`} tick={{ fontSize: 10, fill: INK.muted }} stroke={INK.axis} />
            <YAxis tickFormatter={(v) => fmtMoney(v)} tick={{ fontSize: 10, fill: INK.muted }} stroke={INK.axis} width={56} />
            <ReferenceLine y={0} stroke={INK.secondary} />
            <Tooltip
              cursor={{ fill: "rgba(11,11,11,0.04)" }}
              content={
                <ChartTooltip
                  render={(s) => (
                    <>
                      <div className="font-semibold text-slate-900">{s.discount_pct}% bundle discount</div>
                      <div>+{s.extra_bundles} extra bundles · discount cost {fmtMoney(s.discount_cost)}</div>
                      <div>Δ revenue {fmtMoney(s.delta_revenue)} · Δ gross profit <b>{fmtMoney(s.delta_gross_profit)}</b></div>
                    </>
                  )}
                />
              }
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="delta_revenue" name="Δ revenue" fill={SERIES[0]} radius={4} />
            <Bar dataKey="delta_gross_profit" name="Δ gross profit" fill={SERIES[1]} radius={4} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <Table
        head={
          <>
            <Th>Anchor (A)</Th><Th>Add-on (B)</Th><Th right>Baskets with A</Th><Th right>Baseline attach</Th>
            <Th right>Lift</Th><Th right>Best discount</Th><Th right>Δ gross profit</Th>
          </>
        }
      >
        {data.bundle_pairs.map((p) => (
          <tr key={`${p.anchor_id}-${p.addon_id}`} className="hover:bg-slate-50">
            <Td strong>{p.anchor_name} <span className="text-slate-400 font-normal">{fmtMoney(p.anchor_price, 2)}</span></Td>
            <Td>{p.addon_name} <span className="text-slate-400">{fmtMoney(p.addon_price, 2)}</span></Td>
            <Td right>{p.anchor_baskets}</Td>
            <Td right>{p.baseline_attach_pct}%</Td>
            <Td right>{p.lift}x</Td>
            <Td right>{p.best_discount_pct != null ? `${p.best_discount_pct}%` : <Badge variant="slate">don't discount</Badge>}</Td>
            <Td right strong>{fmtMoney(p.best_delta_gross_profit, 2)}</Td>
          </tr>
        ))}
      </Table>

      <Formula>
        <div>Free shipping at threshold T (v = basket value):</div>
        <div>  nudgeable = baskets with window·T ≤ v &lt; T · converted = nudgeable × conversion</div>
        <div>  uplift = Σ (T − v) over nudgeable × conversion   (converted carts top up exactly to T: a lower bound)</div>
        <div>  net = uplift × margin − (qualifying + converted) × shipping cost</div>
        <div className="pt-1">Bundle with discount d on anchor A + add-on B, over the n(A) baskets containing A:</div>
        <div>  a0 = n(A,B)/n(A) · a1 = min(1, a0·(1 + elasticity·d))</div>
        <div>  Δrevenue = n(A)·[a1·(pA+pB)·(1−d) + (1−a1)·pA] − n(A)·(pA + a0·pB)</div>
        <div>  ΔGP = n(A)·[a1·(pA+pB)·(m−d) + (1−a1)·pA·m] − n(A)·m·(pA + a0·pB)</div>
        <div>  Discount cost includes baskets that would have bought both anyway (cannibalisation).</div>
      </Formula>
    </div>
  );
}
