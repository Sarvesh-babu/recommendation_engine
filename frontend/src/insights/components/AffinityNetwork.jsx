import { useMemo, useState } from "react";
import { Badge, Empty, Formula, ModuleError, SectionHeader, StatCard, Table, Td, Th } from "./ui";
import { INK, categoryColors, fmtMoney, fmtP } from "./format";

const W = 900;
const H = 560;
const PAD = 40;
const ROLE_BADGE = { hub: "emerald", bridge: "violet", standard: "slate", orphan: "rose" };

/** Deterministic pseudo-random in [0,1) from a string, so the layout is stable between renders. */
function hash01(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return ((h >>> 0) % 10000) / 10000;
}

/** Fruchterman–Reingold layout, seeded by category so clusters start apart, then de-overlapped. */
function layout(nodes, edges, radius) {
  const cats = [...new Set(nodes.map((n) => n.category))].sort();
  const k = Math.sqrt((W * H) / Math.max(nodes.length, 1)) * 0.55;
  const pos = {};
  nodes.forEach((n) => {
    const angle = (cats.indexOf(n.category) / cats.length) * 2 * Math.PI;
    pos[n.product_id] = {
      x: W / 2 + Math.cos(angle) * W * 0.25 + (hash01(n.product_id) - 0.5) * 80,
      y: H / 2 + Math.sin(angle) * H * 0.25 + (hash01(n.product_id + "y") - 0.5) * 80,
    };
  });
  const ids = nodes.map((n) => n.product_id);
  let temp = W / 8;
  for (let iter = 0; iter < 300; iter++) {
    const disp = Object.fromEntries(ids.map((id) => [id, { x: 0, y: 0 }]));
    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        const a = pos[ids[i]], b = pos[ids[j]];
        const dx = a.x - b.x, dy = a.y - b.y;
        const d = Math.max(Math.hypot(dx, dy), 0.01);
        const f = (k * k) / d;
        disp[ids[i]].x += (dx / d) * f; disp[ids[i]].y += (dy / d) * f;
        disp[ids[j]].x -= (dx / d) * f; disp[ids[j]].y -= (dy / d) * f;
      }
    }
    edges.forEach((e) => {
      const a = pos[e.source], b = pos[e.target];
      const dx = a.x - b.x, dy = a.y - b.y;
      const d = Math.max(Math.hypot(dx, dy), 0.01);
      const f = (d * d) / k;
      disp[e.source].x -= (dx / d) * f; disp[e.source].y -= (dy / d) * f;
      disp[e.target].x += (dx / d) * f; disp[e.target].y += (dy / d) * f;
    });
    ids.forEach((id) => {
      const p = pos[id], v = disp[id];
      v.x += (W / 2 - p.x) * 0.05; // mild gravity keeps disconnected components on screen
      v.y += (H / 2 - p.y) * 0.05;
      const d = Math.max(Math.hypot(v.x, v.y), 0.01);
      p.x += (v.x / d) * Math.min(d, temp);
      p.y += (v.y / d) * Math.min(d, temp);
    });
    temp *= 0.985;
  }
  // fit to the viewBox
  const xs = ids.map((id) => pos[id].x), ys = ids.map((id) => pos[id].y);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const sx = (W - 2 * PAD) / Math.max(x1 - x0, 1), sy = (H - 2 * PAD) / Math.max(y1 - y0, 1);
  ids.forEach((id) => {
    pos[id] = { x: PAD + (pos[id].x - x0) * sx, y: PAD + (pos[id].y - y0) * sy };
  });
  // collision pass: keep rings and labels from overlapping after scaling
  const r = Object.fromEntries(nodes.map((n) => [n.product_id, radius(n) + 6]));
  for (let iter = 0; iter < 60; iter++) {
    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        const a = pos[ids[i]], b = pos[ids[j]];
        const dx = b.x - a.x, dy = b.y - a.y;
        const d = Math.max(Math.hypot(dx, dy), 0.01);
        const min = r[ids[i]] + r[ids[j]] + 18;
        if (d < min) {
          const push = (min - d) / 2;
          a.x -= (dx / d) * push; a.y -= (dy / d) * push;
          b.x += (dx / d) * push; b.y += (dy / d) * push;
        }
      }
    }
    ids.forEach((id) => {
      pos[id].x = Math.min(W - PAD, Math.max(PAD, pos[id].x));
      pos[id].y = Math.min(H - PAD / 2, Math.max(PAD, pos[id].y));
    });
  }
  return pos;
}

export default function AffinityNetwork({ data }) {
  const [hover, setHover] = useState(null);
  const connected = useMemo(() => (data?.nodes || []).filter((n) => n.degree > 0), [data]);
  const edges = useMemo(() => data?.edges || [], [data]);
  const radius = useMemo(() => {
    const maxRev = Math.max(...connected.map((n) => n.revenue), 1);
    return (n) => 6 + 12 * Math.sqrt(n.revenue / maxRev);
  }, [connected]);
  const pos = useMemo(() => layout(connected, edges, radius), [connected, edges, radius]);
  const colors = useMemo(() => categoryColors((data?.nodes || []).map((n) => n.category)), [data]);
  if (data?.error) return <ModuleError data={data} />;

  const s = data.summary;
  const maxSupport = Math.max(...edges.map((e) => e.support), 1);
  const neighbours = new Set(
    hover ? edges.flatMap((e) => (e.source === hover ? [e.target] : e.target === hover ? [e.source] : [])) : []
  );
  const focus = connected.find((n) => n.product_id === hover);
  const labelled = new Set(
    [...connected].sort((a, b) => b.degree - a.degree || b.revenue - a.revenue).slice(0, 8).map((n) => n.product_id)
  );
  const legendCats = Object.keys(colors).filter((c) => c !== "Unknown" && connected.some((n) => n.category === c));

  return (
    <div>
      <SectionHeader
        title="Product Affinity Network"
        subtitle="Products linked only where they are bought together significantly more often than chance. Node size = revenue, colour = category, line thickness = shared baskets."
      />

      <div className="flex flex-wrap gap-3 mb-4">
        <StatCard label="Significant links" value={s.total_edges} sub={`${s.cross_category_edges} cross-category · ${s.pairs_tested} pairs tested`} />
        <StatCard label="Hubs" value={s.hub_count} sub={`degree ≥ ${s.hub_degree_threshold}`} />
        <StatCard label="Bridges" value={s.bridge_count} sub="partners spread across categories" />
        <StatCard label="Standard" value={s.standard_count} />
        <StatCard label="Orphans" value={s.orphan_count} sub="no significant partner" />
      </div>

      {connected.length === 0 ? (
        <Empty>No product pair passes the significance test — there is not enough co-purchase signal yet.</Empty>
      ) : (
        <div className="rounded-lg border border-slate-200 bg-[#fcfcfb] overflow-x-auto">
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[640px]" role="img" aria-label="Product affinity network">
            {edges.map((e) => {
              const a = pos[e.source], b = pos[e.target];
              const active = hover && (e.source === hover || e.target === hover);
              return (
                <line
                  key={`${e.source}-${e.target}`}
                  x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                  stroke={active ? INK.primary : INK.axis}
                  strokeOpacity={hover && !active ? 0.15 : 0.9}
                  strokeWidth={1 + 4 * (e.support / maxSupport)}
                  strokeDasharray={e.cross_category ? undefined : "4 3"}
                />
              );
            })}
            {connected.map((n) => {
              const p = pos[n.product_id];
              const dim = hover && hover !== n.product_id && !neighbours.has(n.product_id);
              const r = radius(n);
              return (
                <g
                  key={n.product_id}
                  onMouseEnter={() => setHover(n.product_id)}
                  onMouseLeave={() => setHover(null)}
                  opacity={dim ? 0.2 : 1}
                  className="cursor-pointer"
                >
                  <circle cx={p.x} cy={p.y} r={r + 8} fill="transparent" />
                  {n.role === "hub" && <circle cx={p.x} cy={p.y} r={r + 4} fill="none" stroke={INK.primary} strokeWidth={2} />}
                  {n.role === "bridge" && (
                    <circle cx={p.x} cy={p.y} r={r + 4} fill="none" stroke={INK.primary} strokeWidth={1.5} strokeDasharray="3 2" />
                  )}
                  <circle cx={p.x} cy={p.y} r={r} fill={colors[n.category]} stroke="#fcfcfb" strokeWidth={2} />
                  {(labelled.has(n.product_id) || hover === n.product_id || neighbours.has(n.product_id)) && (
                    <text x={p.x} y={p.y - r - 7} textAnchor="middle" fontSize={11} fill={INK.secondary}
                      paintOrder="stroke" stroke="#fcfcfb" strokeWidth={3}>
                      {n.name}
                    </text>
                  )}
                </g>
              );
            })}
          </svg>
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-slate-600">
        {legendCats.map((c) => (
          <span key={c} className="flex items-center gap-1.5 capitalize">
            <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: colors[c] }} />{c}
          </span>
        ))}
        <span className="flex items-center gap-1.5"><span className="inline-block h-3 w-3 rounded-full border-2 border-slate-900" />hub</span>
        <span className="flex items-center gap-1.5"><span className="inline-block h-3 w-3 rounded-full border border-dashed border-slate-900" />bridge</span>
        <span>solid line = cross-category · dashed = same category</span>
      </div>

      <div className="mt-3 min-h-[2.5rem] rounded-md bg-slate-50 border border-slate-200 px-3 py-2 text-[11px] text-slate-700">
        {focus ? (
          <>
            <b>{focus.name}</b> <span className="capitalize">({focus.category})</span> · <Badge variant={ROLE_BADGE[focus.role]}>{focus.role}</Badge>{" "}
            · {focus.degree} links · participation {focus.participation} · revenue {fmtMoney(focus.revenue)} · partners:{" "}
            {edges
              .filter((e) => e.source === focus.product_id || e.target === focus.product_id)
              .map((e) => {
                const other = connected.find((n) => n.product_id === (e.source === focus.product_id ? e.target : e.source));
                return `${other?.name} (${e.lift}x, q ${fmtP(e.q_value)})`;
              })
              .join("; ")}
          </>
        ) : (
          <span className="text-slate-400">Hover a product to see its partners.</span>
        )}
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-2">Most connected products</h3>
          <Table head={<><Th>Product</Th><Th>Category</Th><Th right>Links</Th><Th right>Participation</Th><Th>Role</Th></>}>
            {connected.slice(0, 12).map((n) => (
              <tr key={n.product_id} className="hover:bg-slate-50">
                <Td strong>{n.name}</Td>
                <Td className="capitalize">{n.category}</Td>
                <Td right>{n.degree}</Td>
                <Td right>{n.participation}</Td>
                <Td><Badge variant={ROLE_BADGE[n.role]}>{n.role}</Badge></Td>
              </tr>
            ))}
          </Table>
        </div>
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-2">Orphans by revenue</h3>
          {data.orphans.length === 0 ? (
            <Empty>Every product has at least one significant partner.</Empty>
          ) : (
            <Table head={<><Th>Product</Th><Th>Category</Th><Th right>Baskets</Th><Th right>Revenue</Th></>}>
              {data.orphans.slice(0, 12).map((n) => (
                <tr key={n.product_id} className="hover:bg-slate-50">
                  <Td strong>{n.name}</Td>
                  <Td className="capitalize">{n.category}</Td>
                  <Td right>{n.baskets}</Td>
                  <Td right>{fmtMoney(n.revenue)}</Td>
                </tr>
              ))}
            </Table>
          )}
        </div>
      </div>

      <Formula>
        <div>edge A–B ⇔ n(A,B) ≥ {data.params.min_support}, lift &gt; 1, BH q &lt; {data.params.alpha} (one-sided Fisher / hypergeometric)</div>
        <div>degree k = number of links · participation P = 1 − Σ_c (k_c / k)²</div>
        <div>hub: k ≥ max(3, P90 of k) · bridge: k ≥ 2, P ≥ 0.5, partners in ≥ 2 other categories · orphan: k = 0</div>
        <div>density = 2·edges / (n·(n−1)) = {s.density}</div>
      </Formula>
    </div>
  );
}
