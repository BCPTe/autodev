import { Link } from "react-router-dom"
import { PageHeader } from "@/components/PageHeader"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useCosts } from "@/hooks/queries"
import { money, shortModel, tokens } from "@/lib/format"
import { KIND_LABEL } from "@/lib/status"
import { cn } from "@/lib/utils"
import type { Costs as CostsData } from "@/lib/api"

const label = (kind: string) => KIND_LABEL[kind as keyof typeof KIND_LABEL] ?? kind

function ByArea({ rows }: { rows: CostsData["by_area"] }) {
  const areas = [...new Set(rows.map((r) => r.area))]
  const cell = (kind: string, area: string) => rows.find((r) => r.kind === kind && r.area === area)
  return (
    <Table>
      <TableHeader><TableRow><TableHead>Area</TableHead><TableHead className="text-right">Triage (avg)</TableHead><TableHead className="text-right">Fix (avg)</TableHead></TableRow></TableHeader>
      <TableBody>
        {areas.map((a) => (
          <TableRow key={a}>
            <TableCell>{a}</TableCell>
            {["triage", "fix"].map((k) => {
              const r = cell(k, a)
              return <TableCell key={k} className="text-right tabular-nums">{r ? <>{money(r.avg_cost)} <span className="text-muted-foreground">· {r.runs}</span></> : "—"}</TableCell>
            })}
          </TableRow>
        ))}
        {areas.length === 0 && <TableRow><TableCell colSpan={3} className="text-muted-foreground">No data.</TableCell></TableRow>}
      </TableBody>
    </Table>
  )
}

function DayBars({ days, cap }: { days: { day: string; cost: number; runs: number }[]; cap: number }) {
  if (days.length === 0) return <p className="text-muted-foreground">No spending recorded in the last 30 days.</p>
  const max = Math.max(cap, ...days.map((d) => d.cost)) * 1.05
  return (
    <figure>
      <div className="relative flex h-40 items-end gap-1 border-b" role="img" aria-label={`Daily spend, peak ${money(Math.max(...days.map((d) => d.cost)))}`}>
        <div className="absolute inset-x-0 border-t border-dashed border-lamp-red/70" style={{ bottom: `${(cap / max) * 100}%` }} />
        <span className="absolute right-0 text-xs text-lamp-red" style={{ bottom: `calc(${(cap / max) * 100}% + 2px)` }}>cap {money(cap)}</span>
        {days.map((d) => (
          <div key={d.day} className="group relative flex h-full min-w-2 flex-1 items-end">
            <div className={cn("w-full rounded-t-sm", d.cost >= cap ? "bg-lamp-red" : "bg-primary")} style={{ height: `${(d.cost / max) * 100}%`, minHeight: d.cost > 0 ? 2 : 0 }} />
            <span className="pointer-events-none absolute -top-8 left-1/2 -translate-x-1/2 origin-bottom scale-95 whitespace-nowrap rounded-sm border bg-popover px-2 py-1 text-xs opacity-0 shadow transition-[opacity,transform] duration-150 ease-out [@media(hover:hover)]:group-hover:scale-100 [@media(hover:hover)]:group-hover:opacity-100">
              {d.day}: {money(d.cost)} · {d.runs} {d.runs === 1 ? "run" : "runs"}
            </span>
          </div>
        ))}
      </div>
      <figcaption className="mt-1 flex justify-between text-xs text-muted-foreground"><span>{days[0].day}</span><span>{days[days.length - 1].day}</span></figcaption>
    </figure>
  )
}

export function Costs() {
  const { data: c, isLoading } = useCosts()
  if (isLoading || !c) return <Skeleton className="h-64 w-full" />
  const pct = Math.min(100, (c.today / c.daily_cap) * 100)

  return (
    <>
      <PageHeader title="Costs">Dollar-equivalent figures. On a subscription you are not billed, but they count against your quota</PageHeader>

      <section className="grid gap-x-10 gap-y-8 lg:grid-cols-2">
        <div className="space-y-5">
          <div>
            <p className="text-sm text-muted-foreground">Today against the daily cap</p>
            <p className="mt-1 font-display text-4xl leading-none tabular-nums">{money(c.today)} <span className="text-lg text-muted-foreground">/ {money(c.daily_cap)}</span></p>
            <div role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label="Daily budget" className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
              <div className={cn("h-full rounded-full transition-[width] duration-200 ease-out", pct >= 80 ? "bg-lamp-red" : "bg-primary")} style={{ width: `${pct}%` }} />
            </div>
          </div>
          <dl className="grid divide-y border-y">
            <div className="flex items-baseline justify-between py-2"><dt className="text-sm text-muted-foreground">All-time total</dt><dd className="font-display text-xl tabular-nums">{money(c.total)}</dd></div>
            <div className="flex items-baseline justify-between py-2"><dt className="text-sm text-muted-foreground">Cap per ticket</dt><dd className="font-display text-xl tabular-nums">{money(c.ticket_cap)}</dd></div>
          </dl>
        </div>
        <div>
          <h2 className="section-title">Last 30 days</h2>
          <DayBars days={c.by_day} cap={c.daily_cap} />
        </div>
      </section>

      <section className="mt-8">
        <h2 className="section-title">Tokens and cost by stage and model</h2>
        <p className="mb-2 text-xs text-muted-foreground">Above about 100k tokens of context every token costs several times more: keep the peak below it.</p>
        <Table className="text-[13px]">
          <TableHeader>
            <TableRow>
              <TableHead>Stage</TableHead><TableHead>Model</TableHead>
              <TableHead className="text-right">Sessions</TableHead>
              <TableHead className="text-right">Input</TableHead><TableHead className="text-right">Output</TableHead>
              <TableHead className="text-right">Cache read</TableHead><TableHead className="text-right">Cache write</TableHead>
              <TableHead className="text-right">Peak context</TableHead><TableHead className="text-right">Cost</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {c.by_stage_model.map((r) => (
              <TableRow key={`${r.kind}-${r.model}`}>
                <TableCell>{label(r.kind)}</TableCell>
                <TableCell>{shortModel(r.model)}</TableCell>
                <TableCell className="text-right tabular-nums">{r.sessions}</TableCell>
                {r.untracked >= r.sessions
                  ? <TableCell colSpan={4} className="text-right text-muted-foreground">tokens not recorded</TableCell>
                  : [r.input, r.output, r.cache_read, r.cache_write].map((v, i) => <TableCell key={i} className="text-right tabular-nums">{tokens(v)}</TableCell>)}
                <TableCell className={cn("text-right tabular-nums", r.long_context > 0 && "text-lamp-red")} title={r.long_context > 0 ? `${r.long_context} session(s) went over 100k tokens of context, billed at a much higher rate` : undefined}>{r.peak_context > 0 ? tokens(r.peak_context) : "—"}</TableCell>
                <TableCell className="text-right tabular-nums">{money(r.cost)}</TableCell>
              </TableRow>
            ))}
            {c.by_stage_model.length === 0 && <TableRow><TableCell colSpan={9} className="text-muted-foreground">No data.</TableCell></TableRow>}
          </TableBody>
        </Table>
      </section>

      <div className="mt-8 grid gap-x-10 gap-y-8 text-[13px] lg:grid-cols-2">
        <section>
          <h2 className="section-title">Most expensive tickets</h2>
          <Table>
            <TableHeader><TableRow><TableHead>Ticket</TableHead><TableHead className="text-right">Runs</TableHead><TableHead className="text-right">Cost</TableHead></TableRow></TableHeader>
            <TableBody>
              {c.by_ticket.map((t) => (
                <TableRow key={t.ticket_id}>
                  <TableCell className="max-w-[18rem] truncate"><Link to={`/tickets/${t.ticket_id}`} className="underline-offset-4 hover:underline">{t.title}</Link></TableCell>
                  <TableCell className="text-right tabular-nums">{t.runs}</TableCell>
                  <TableCell className={cn("text-right tabular-nums", t.cost >= c.ticket_cap && "text-lamp-red")}>{money(t.cost)}</TableCell>
                </TableRow>
              ))}
              {c.by_ticket.length === 0 && <TableRow><TableCell colSpan={3} className="text-muted-foreground">No runs recorded yet.</TableCell></TableRow>}
            </TableBody>
          </Table>
        </section>
        <section>
          <h2 className="section-title">Cost per outcome</h2>
          <Table>
            <TableHeader><TableRow><TableHead>Run</TableHead><TableHead>Outcome</TableHead><TableHead className="text-right">Runs</TableHead><TableHead className="text-right">Average</TableHead><TableHead className="text-right">Total</TableHead></TableRow></TableHeader>
            <TableBody>
              {c.by_outcome.runs.map((o) => (
                <TableRow key={`${o.kind}-${o.outcome}`}><TableCell>{label(o.kind)}</TableCell><TableCell>{o.outcome}</TableCell><TableCell className="text-right tabular-nums">{o.runs}</TableCell><TableCell className="text-right tabular-nums">{money(o.avg_cost)}</TableCell><TableCell className="text-right tabular-nums">{money(o.cost)}</TableCell></TableRow>
              ))}
              {c.by_outcome.runs.length === 0 && <TableRow><TableCell colSpan={5} className="text-muted-foreground">No data.</TableCell></TableRow>}
            </TableBody>
          </Table>
          {c.by_outcome.tickets.length > 0 && (
            <>
              <p className="mb-1 mt-4 text-xs text-muted-foreground">Whole ticket (triage, fixes and retrospective), by how its last fix ended</p>
              <Table>
                <TableHeader><TableRow><TableHead>Last fix</TableHead><TableHead className="text-right">Tickets</TableHead><TableHead className="text-right">Average</TableHead><TableHead className="text-right">Total</TableHead></TableRow></TableHeader>
                <TableBody>
                  {c.by_outcome.tickets.map((o) => (
                    <TableRow key={o.outcome}><TableCell>{o.outcome}</TableCell><TableCell className="text-right tabular-nums">{o.tickets}</TableCell><TableCell className="text-right tabular-nums">{money(o.avg_cost)}</TableCell><TableCell className="text-right tabular-nums">{money(o.cost)}</TableCell></TableRow>
                  ))}
                </TableBody>
              </Table>
            </>
          )}
        </section>
        <section>
          <h2 className="section-title">Average cost per area</h2>
          <ByArea rows={c.by_area} />
        </section>
      </div>

    </>
  )
}
