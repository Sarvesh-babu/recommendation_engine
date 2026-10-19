import { Empty, Formula, ModuleError, SectionHeader, StatCard, Table, Td, Th } from "./ui";
import { SERIES, fmtMoney, fmtNum, fmtP } from "./format";

export default function RevenueOpportunity({ data }) {
  if (data?.error) return <ModuleError data={data} />;
  const opps = data.top_opportunities;
  const chart = opps.slice(0, 10).map((o) => ({ ...o, label: `${o.source_product_name} → ${o.target_product_name}` }));
  const maxValue = Math.max(...chart.map((o) => o.addressable_revenue), 1);

  return (
    <div>
      <SectionHeader
        title="Revenue Opportunity Sizing"
        subtitle="Cross-sell rules A → B from statistically significant pairs. Sized as the revenue you'd gain if A-buyers who haven't bought B yet adopt it at the excess rate their peers show over the general population."
      />

      <div className="flex flex-wrap gap-3 mb-5">
        <StatCard label="Addressable revenue" value={fmtMoney(data.total_addressable_revenue)} sub={`top ${opps.length} rules`} />
        <StatCard label="Share of realised revenue" value={`${data.addressable_pct_of_revenue}%`} sub={`of ${fmtMoney(data.realised_revenue)}`} />
        <StatCard label="Significant pairs" value={data.significant_pairs} sub={`of ${fmtNum(data.pairs_tested)} pairs tested`} />
        <StatCard label="Rules with upside" value={data.rules_with_opportunity} sub="incremental attach > 0" />
      </div>

      {opps.length === 0 ? (
        <Empty>No significant cross-sell associations with remaining upside were found.</Empty>
      ) : (
        <>
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-2">Top 10 by addressable revenue</h3>
          <ol className="mb-5 space-y-1.5">
            {chart.map((o) => (
              <li key={o.label} className="group grid grid-cols-[minmax(0,16rem)_1fr_5rem] items-center gap-3 text-[11px]">
                <span className="truncate text-slate-600" title={o.label}>{o.label}</span>
                <span className="relative h-4 rounded bg-slate-100">
                  <span
                    className="absolute inset-y-0 left-0 rounded-r"
                    style={{ width: `${(o.addressable_revenue / maxValue) * 100}%`, background: SERIES[0] }}
                  />
                  <span className="pointer-events-none absolute left-2 top-5 z-10 hidden whitespace-nowrap rounded-md border border-slate-200 bg-white px-3 py-2 shadow-lg group-hover:block">
                    {o.gap_customers} gap customers × {o.incremental_attach_pct}% incremental attach × {fmtMoney(o.target_price, 2)} ={" "}
                    <b>{fmtMoney(o.addressable_revenue, 2)}</b>
                  </span>
                </span>
                <span className="text-right font-semibold tabular-nums text-slate-900">{fmtMoney(o.addressable_revenue)}</span>
              </li>
            ))}
          </ol>

          <Table
            head={
              <>
                <Th>#</Th><Th>Source (A)</Th><Th>Target (B)</Th><Th right>Lift</Th><Th right>q</Th>
                <Th right>A buyers</Th><Th right>Gap</Th><Th right>Attach</Th><Th right>Base</Th>
                <Th right>Incremental</Th><Th right>Price B</Th><Th right>Addressable</Th>
              </>
            }
          >
            {opps.map((o, i) => (
              <tr key={`${o.source_product_id}-${o.target_product_id}`} className="hover:bg-slate-50">
                <Td>{i + 1}</Td>
                <Td strong>{o.source_product_name}</Td>
                <Td>{o.target_product_name}</Td>
                <Td right>{o.lift}x</Td>
                <Td right>{fmtP(o.q_value)}</Td>
                <Td right>{o.source_customers}</Td>
                <Td right>{o.gap_customers}</Td>
                <Td right>{o.attach_rate_pct}%</Td>
                <Td right>{o.base_rate_pct}%</Td>
                <Td right>{o.incremental_attach_pct}%</Td>
                <Td right>{fmtMoney(o.target_price, 2)}</Td>
                <Td right strong>{fmtMoney(o.addressable_revenue, 2)}</Td>
              </tr>
            ))}
          </Table>
        </>
      )}

      <Formula>
        <div>attach(A→B) = |customers who bought A and B| / |customers who bought A|</div>
        <div>base(B) = |customers who bought B| / |all customers|</div>
        <div>gap = |A buyers| − |A buyers who already bought B|</div>
        <div>addressable = gap × (attach − base) × price(B)</div>
        <div>Only pairs with lift &gt; 1 and Benjamini–Hochberg q &lt; {data.alpha} are considered.</div>
      </Formula>
    </div>
  );
}
