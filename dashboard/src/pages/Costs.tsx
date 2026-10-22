import { PageHeader } from "@/components/PageHeader"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useCosts } from "@/hooks/queries"
import { money, shortModel } from "@/lib/format"
import { cn } from "@/lib/utils"

function DayBars({ days, cap }: { days: { day: string; cost: number; runs: number }[]; cap: number }) {
  if (days.length === 0) return <p className="text-muted-foreground">No spending recorded in the last 30 days.</p>
  const max = Math.max(cap, ...days.map((d) => d.cost)) * 1.05
  return (
    <figure>
      <div className="relative flex h-52 items-end gap-1.5 border-b" role="img" aria-label={`Daily spend, peak ${money(Math.max(...days.map((d) => d.cost)))}`}>
        <div className="absolute inset-x-0 border-t border-dashed border-lamp-red/70" style={{ bottom: `${(cap / max) * 100}%` }} />
        <span className="absolute right-0 text-xs text-lamp-red" style={{ bottom: `calc(${(cap / max) * 100}% + 2px)` }}>cap {money(cap)}</span>
        {days.map((d) => (
          <div key={d.day} className="group relative flex h-full min-w-2 flex-1 items-end">
            <div className={cn("w-full rounded-t-sm", d.cost >= cap ? "bg-lamp-red" : "bg-primary")} style={{ height: `${(d.cost / max) * 100}%`, minHeight: d.cost > 0 ? 2 : 0 }} />
            <span className="pointer-events-none absolute -top-8 left-1/2 hidden -translate-x-1/2 whitespace-nowrap rounded-sm border bg-popover px-2 py-1 text-xs shadow group-hover:block">
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

      <section className="grid gap-x-12 gap-y-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div>
          <p className="text-sm text-muted-foreground">Today against the daily cap</p>
          <p className="mt-1 font-display text-6xl leading-none tabular-nums">{money(c.today)} <span className="text-2xl text-muted-foreground">/ {money(c.daily_cap)}</span></p>
          <div role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label="Daily budget" className="mt-4 h-2 overflow-hidden rounded-full bg-muted">
            <div className={cn("h-full rounded-full", pct >= 80 ? "bg-lamp-red" : "bg-primary")} style={{ width: `${pct}%` }} />
          </div>
        </div>
        <dl className="grid content-end divide-y border-y">
          <div className="flex items-baseline justify-between py-3"><dt className="text-muted-foreground">All-time total</dt><dd className="font-display text-2xl tabular-nums">{money(c.total)}</dd></div>
          <div className="flex items-baseline justify-between py-3"><dt className="text-muted-foreground">Cap per ticket</dt><dd className="font-display text-2xl tabular-nums">{money(c.ticket_cap)}</dd></div>
        </dl>
      </section>

      <section className="mt-14">
        <h2 className="section-title">Last 30 days</h2>
        <DayBars days={c.by_day} cap={c.daily_cap} />
      </section>

      <div className="mt-14 grid gap-12 lg:grid-cols-2">
        <section>
          <h2 className="section-title">By model</h2>
          <Table>
            <TableHeader><TableRow><TableHead>Model</TableHead><TableHead className="text-right">Runs</TableHead><TableHead className="text-right">Cost</TableHead></TableRow></TableHeader>
            <TableBody>
              {c.by_model.map((m) => (
                <TableRow key={m.model}><TableCell>{shortModel(m.model)}</TableCell><TableCell className="text-right tabular-nums">{m.runs}</TableCell><TableCell className="text-right tabular-nums">{money(m.cost)}</TableCell></TableRow>
              ))}
              {c.by_model.length === 0 && <TableRow><TableCell colSpan={3} className="text-muted-foreground">No runs recorded yet.</TableCell></TableRow>}
            </TableBody>
          </Table>
        </section>
        <section>
          <h2 className="section-title">Most expensive tickets</h2>
          <Table>
            <TableHeader><TableRow><TableHead>Ticket</TableHead><TableHead className="text-right">Runs</TableHead><TableHead className="text-right">Cost</TableHead></TableRow></TableHeader>
            <TableBody>
              {c.by_ticket.map((t) => (
                <TableRow key={t.ticket_id}>
                  <TableCell className="max-w-[18rem] truncate">{t.title}</TableCell>
                  <TableCell className="text-right tabular-nums">{t.runs}</TableCell>
                  <TableCell className={cn("text-right tabular-nums", t.cost >= c.ticket_cap && "text-lamp-red")}>{money(t.cost)}</TableCell>
                </TableRow>
              ))}
              {c.by_ticket.length === 0 && <TableRow><TableCell colSpan={3} className="text-muted-foreground">No runs recorded yet.</TableCell></TableRow>}
            </TableBody>
          </Table>
        </section>
      </div>
    </>
  )
}
