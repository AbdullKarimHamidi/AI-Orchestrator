import { fmtInt, fmtUsd } from "@/lib/format"
import type { TimeseriesRow } from "@/lib/schemas"

/** Stacked daily bars (completed / failed / other) with cost underneath. Plain SVG, no chart library. */
export function DailyChart({ rows }: { rows: TimeseriesRow[] }) {
  const max = Math.max(1, ...rows.map((r) => r.runs))
  const W = 720
  const H = 180
  const bw = W / Math.max(rows.length, 1)
  const y = (v: number) => (v / max) * (H - 20)
  const label = (i: number) => rows.length <= 14 || i % Math.ceil(rows.length / 10) === 0
  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H + 24}`} className="h-56 w-full" role="img" aria-label={`Runs per day, ${rows.length} days, peak ${max}`}>
        {[0.25, 0.5, 0.75, 1].map((f) => <line key={f} x1={0} x2={W} y1={H - y(max * f)} y2={H - y(max * f)} className="stroke-border" strokeDasharray="3 3" />)}
        {rows.map((r, i) => {
          const x = i * bw + bw * 0.15
          const w = bw * 0.7
          const hc = y(r.completed)
          const hf = y(r.failed)
          const ho = y(r.other)
          return (
            <g key={r.date}>
              <title>{`${r.date}: ${r.runs} runs (${r.completed} completed, ${r.failed} failed, ${r.other} other) · ${fmtInt(r.tokens)} tokens · ${fmtUsd(r.cost_usd)}`}</title>
              <rect x={x} y={H - hc} width={w} height={hc} className="fill-emerald-500" rx={1} />
              <rect x={x} y={H - hc - hf} width={w} height={hf} className="fill-red-500" rx={1} />
              <rect x={x} y={H - hc - hf - ho} width={w} height={ho} className="fill-slate-400" rx={1} />
              {label(i) && <text x={x + w / 2} y={H + 16} textAnchor="middle" className="fill-muted-foreground text-[10px]">{r.date.slice(5)}</text>}
            </g>
          )
        })}
        <line x1={0} x2={W} y1={H} y2={H} className="stroke-border" />
      </svg>
      <figcaption className="flex flex-wrap gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1"><span className="size-2 rounded-sm bg-emerald-500" /> completed</span>
        <span className="flex items-center gap-1"><span className="size-2 rounded-sm bg-red-500" /> failed</span>
        <span className="flex items-center gap-1"><span className="size-2 rounded-sm bg-slate-400" /> cancelled / timed out / in flight</span>
        <span>Peak: {max} runs/day</span>
      </figcaption>
    </figure>
  )
}
