import { useMemo, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { PageHeader } from "@/components/PageHeader"
import { StateLabel } from "@/components/StateLabel"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useTickets } from "@/hooks/queries"
import { ago, money } from "@/lib/format"
import { STATES } from "@/lib/status"
import { cn } from "@/lib/utils"
import type { TicketState } from "@/lib/api"

const ALL = Object.keys(STATES) as TicketState[]

export function Tickets() {
  const { data, isLoading } = useTickets()
  const [q, setQ] = useState("")
  const [state, setState] = useState<TicketState | null>(null)
  const [, setParams] = useSearchParams()

  const counts = useMemo(() => {
    const c: Partial<Record<TicketState, number>> = {}
    data?.tickets.forEach((t) => { c[t.status] = (c[t.status] ?? 0) + 1 })
    return c
  }, [data])

  const rows = (data?.tickets ?? [])
    .filter((t) => (!state || t.status === state) && t.title.toLowerCase().includes(q.toLowerCase()))
    .sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""))

  return (
    <>
      <PageHeader title="Ticket">{data && `${data.tickets.length} in total`}</PageHeader>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by title" aria-label="Cerca per titolo" className="w-64" />
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by status">
          {ALL.filter((s) => counts[s]).map((s) => (
            <button
              key={s}
              onClick={() => setState(state === s ? null : s)}
              aria-pressed={state === s}
              className={cn("rounded-sm border px-2.5 py-1 text-[13px] hover:bg-muted", state === s && "border-primary bg-accent text-accent-foreground")}
            >
              {STATES[s].label} <span className="tabular-nums text-muted-foreground">{counts[s]}</span>
            </button>
          ))}
        </div>
      </div>

      {isLoading && <Skeleton className="h-64 w-full" />}
      {data && rows.length === 0 && <p className="py-6 text-muted-foreground">No ticket matches the filters.</p>}
      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-sm border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Status</TableHead>
                <TableHead>Title</TableHead>
                <TableHead>Area</TableHead>
                <TableHead>Risk</TableHead>
                <TableHead>Model</TableHead>
                <TableHead className="text-right">Attempts</TableHead>
                <TableHead className="text-right">Cost</TableHead>
                <TableHead>Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((t) => (
                <TableRow
                  key={t.id}
                  tabIndex={0}
                  role="link"
                  onClick={() => setParams({ ticket: t.id })}
                  onKeyDown={(e) => e.key === "Enter" && setParams({ ticket: t.id })}
                  className="cursor-pointer"
                >
                  <TableCell><StateLabel state={t.status} /></TableCell>
                  <TableCell className="max-w-[28rem] truncate font-medium">{t.title}</TableCell>
                  <TableCell>{t.area ?? "—"}</TableCell>
                  <TableCell>{t.risk ?? "—"}</TableCell>
                  <TableCell>{t.model ?? "Auto"}</TableCell>
                  <TableCell className="text-right tabular-nums">{t.attempts}</TableCell>
                  <TableCell className="text-right tabular-nums">{money(t.cost_usd)}</TableCell>
                  <TableCell className="whitespace-nowrap text-muted-foreground">{ago(t.updated_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </>
  )
}
