import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Badge, Formula, ModuleError, SectionHeader, StatCard, Table, Td, Th } from "./ui";
import { INK, SERIES, categoryColors, fmtMoney, fmtP } from "./format";

const TREND_BADGE = { evergreen: "emerald", seasonal: "amber", sporadic: "rose", rising: "emerald", falling: "rose", stable: "slate" };

function Sparkline({ values }) {
  const w = 96, h = 24, max = Math.max(...values, 100);
  const pts = values.map((v, i) => `${(i / Math.max(values.length - 1, 1)) * w},${h - (v / max) * h}`).join(" ");
  const base = h - (100 / max) * h;
  return (
    <svg width={w} height={h} className="overflow-visible" aria-hidden>
      <line x1={0} x2={w} y1={base} y2={base} stroke={INK.axis} strokeDasharray="2 2" />
      <polyline points={pts} fill="none" stroke={SERIES[0]} strokeWidth={2} strokeLinejoin="round" />
    </svg>
  );
}

function MultiTooltip({ active, payload, label, unit }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-slate-200 bg-white px-3 py-2 text-[11px] shadow-lg">
      <div className="font-semibold text-slate-900 mb-1">{label}</div>
      {[...payload].sort((a, b) => b.value - a.value).map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2 text-slate-700">
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: p.color }} />
          <span className="capitalize">{p.dataKey}</span>
          <span className="ml-auto font-semibold tabular-nums">{p.value}{unit}</span>
        </div>
      ))}
    </div>
  );
}

export default function SeasonalTrends({ data }) {
  const [selected, setSelected] = useState(0);
  if (data?.error) return <ModuleError data={data} />;

  const months = data.months;
  const cats = data.category_trends.map((c) => c.category);
  const colors = categoryColors(cats);
  const volume = months.map((m) => ({ month: m, baskets: data.monthly_baskets[m], revenue: data.monthly_revenue[m] }));
  const shares = months.map((m) => Object.fromEntries([["month", m], ...data.category_trends.map((c) => [c.category, c.monthly_share_pct[m]])]));
  const pair = data.trends[selected];
  const pairSeries = pair ? months.map((m) => ({ month: m, index: pair.monthly_index[m], count: pair.monthly_counts[m] })) : [];
  const s = data.summary;
  const partial = new Set(data.partial_months);
  const tickMonth = (m) => (partial.has(m) ? `${m}*` : m);

  return (
    <div>
      <SectionHeader
        title="Seasonal Trend Detector"
        subtitle="Monthly co-purchase rates and category shares, normalised by basket volume so busy months don't look 'seasonal'. A pair is seasonal only when its monthly pattern differs significantly from overall traffic."
      />

      <div className="flex flex-wrap gap-3 mb-5">
        <StatCard label="Months" value={months.length} sub={data.partial_months.length ? `* partial: ${data.partial_months.join(", ")}` : "all complete"} />
        <StatCard label="Evergreen pairs" value={s.evergreen_count} sub="steady with traffic" />
        <StatCard label="Seasonal pairs" value={s.seasonal_count} sub={`χ² p < ${data.params.alpha}`} />
        <StatCard label="Sporadic pairs" value={s.sporadic_count} sub="present in < 60% of months" />
        <StatCard label="Category momentum" value={`${s.rising_categories.length}↑ ${s.falling_categories.length}↓`}
          sub={[...s.rising_categories, ...s.falling_categories].join(", ") || "no significant trend"} />
      </div>

      <div className="grid gap-5 lg:grid-cols-2 mb-5">
        <div>
          <p className="text-[11px] text-slate-500 mb-1">Baskets per month</p>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={volume} margin={{ left: 0, right: 8, top: 8 }}>
                <CartesianGrid vertical={false} stroke={INK.grid} />
                <XAxis dataKey="month" tickFormatter={tickMonth} tick={{ fontSize: 10, fill: INK.muted }} stroke={INK.axis} />
                <YAxis tick={{ fontSize: 10, fill: INK.muted }} stroke={INK.axis} width={36} />
                <Tooltip
                  cursor={{ fill: "rgba(11,11,11,0.04)" }}
                  content={({ active, payload, label }) =>
                    active && payload?.length ? (
                      <div className="rounded-md border border-slate-200 bg-white px-3 py-2 text-[11px] shadow-lg">
                        <b>{label}</b>: {payload[0].payload.baskets} baskets · revenue {fmtMoney(payload[0].payload.revenue)}
                      </div>
                    ) : null
                  }
                />
                <Bar dataKey="baskets" fill={SERIES[0]} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div>
          <p className="text-[11px] text-slate-500 mb-1">Category share of baskets (%)</p>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={shares} margin={{ left: 0, right: 8, top: 8 }}>
                <CartesianGrid vertical={false} stroke={INK.grid} />
                <XAxis dataKey="month" tickFormatter={tickMonth} tick={{ fontSize: 10, fill: INK.muted }} stroke={INK.axis} />
                <YAxis tick={{ fontSize: 10, fill: INK.muted }} stroke={INK.axis} width={36} unit="%" />
                <Tooltip content={<MultiTooltip unit="%" />} />
                <Legend wrapperStyle={{ fontSize: 11 }} formatter={(v) => <span className="capitalize text-slate-700">{v}</span>} />
                {cats.map((c) => (
                  <Line key={c} dataKey={c} stroke={colors[c]} strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-2">Category momentum</h3>
      <div className="mb-6">
        <Table head={<><Th>Category</Th><Th right>Mean share</Th><Th right>Slope (pp/month)</Th><Th right>Relative / month</Th><Th right>R²</Th><Th right>p</Th><Th>Trend</Th><Th>Peak</Th></>}>
          {data.category_trends.map((c) => (
            <tr key={c.category} className="hover:bg-slate-50">
              <Td strong className="capitalize">{c.category}</Td>
              <Td right>{c.mean_share_pct}%</Td>
              <Td right>{c.slope_pp_per_month > 0 ? "+" : ""}{c.slope_pp_per_month}</Td>
              <Td right>{c.relative_change_per_month_pct > 0 ? "+" : ""}{c.relative_change_per_month_pct}%</Td>
              <Td right>{c.r_squared}</Td>
              <Td right>{fmtP(c.p_value)}</Td>
              <Td><Badge variant={TREND_BADGE[c.trend]}>{c.trend}</Badge></Td>
              <Td>{tickMonth(c.peak_month)}</Td>
            </tr>
          ))}
        </Table>
      </div>

      <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-2">Top product pairs — click a row to chart it</h3>
      <div className="grid gap-5 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <Table head={<><Th>Pair</Th><Th right>Support</Th><Th right>Presence</Th><Th right>CV</Th><Th right>χ² p</Th><Th>Index</Th><Th>Class</Th></>}>
            {data.trends.map((t, i) => (
              <tr key={`${t.product_a_id}-${t.product_b_id}`} onClick={() => setSelected(i)}
                className={`cursor-pointer ${i === selected ? "bg-sky-50" : "hover:bg-slate-50"}`}>
                <Td strong>{t.product_a_name} + {t.product_b_name}</Td>
                <Td right>{t.total_support}</Td>
                <Td right>{t.months_present}/{t.total_months}</Td>
                <Td right>{t.coefficient_of_variation}</Td>
                <Td right className="whitespace-nowrap">{fmtP(t.p_value)}{t.low_expected_counts && <span title="Expected counts < 5: χ² is approximate">†</span>}</Td>
                <Td><Sparkline values={months.map((m) => t.monthly_index[m])} /></Td>
                <Td><Badge variant={TREND_BADGE[t.trend_type]}>{t.trend_type}</Badge></Td>
              </tr>
            ))}
          </Table>
          <p className="mt-1 text-[10px] text-slate-500">† expected monthly counts below 5, so the χ² p-value is approximate. Treat the class as indicative.</p>
        </div>
        <div className="lg:col-span-2">
          {pair && (
            <>
              <p className="text-[11px] text-slate-500 mb-1">
                <b className="text-slate-800">{pair.product_a_name} + {pair.product_b_name}</b>: seasonal index (100 = average month)
              </p>
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={pairSeries} margin={{ left: 0, right: 12, top: 8 }}>
                    <CartesianGrid vertical={false} stroke={INK.grid} />
                    <XAxis dataKey="month" tickFormatter={tickMonth} tick={{ fontSize: 10, fill: INK.muted }} stroke={INK.axis} />
                    <YAxis tick={{ fontSize: 10, fill: INK.muted }} stroke={INK.axis} width={36} />
                    <ReferenceLine y={100} stroke={INK.secondary} strokeDasharray="4 3" />
                    <Tooltip
                      content={({ active, payload, label }) =>
                        active && payload?.length ? (
                          <div className="rounded-md border border-slate-200 bg-white px-3 py-2 text-[11px] shadow-lg">
                            <b>{label}</b>: index {payload[0].payload.index} · {payload[0].payload.count} co-purchases
                          </div>
                        ) : null
                      }
                    />
                    <Line dataKey="index" stroke={SERIES[0]} strokeWidth={2} dot={{ r: 4 }} activeDot={{ r: 6 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <p className="text-[11px] text-slate-600">
                Peak {pair.peak_month} at {pair.peak_index} · χ² = {pair.chi2}, p = {fmtP(pair.p_value)} → <b>{pair.trend_type}</b>
              </p>
            </>
          )}
        </div>
      </div>

      <Formula>
        <div>B_m = baskets in month m · rate_m = n_m(A,B) / B_m · index_m = rate_m / mean(rate) × 100</div>
        <div>CV = std(rate) / mean(rate)  (population std)</div>
        <div>χ²: observed n_m(A,B) vs expected n(A,B) · B_m / N → seasonal if p &lt; {data.params.alpha}; else evergreen if present in ≥ 60% of months; else sporadic</div>
        <div>Category momentum: OLS of share_m = baskets with category / B_m on month number; rising/falling if slope p &lt; {data.params.alpha}</div>
      </Formula>
    </div>
  );
}
