import { useState, type ReactNode } from "react"
import { useNavigate } from "react-router-dom"
import { Activity, Clock, Coins, Cpu, Folder, RotateCw, ShieldAlert, Type, X, ChevronDown, ListFilter, type LucideIcon } from "lucide-react"
import { PageHeader } from "@/components/PageHeader"
import { Lamp } from "@/components/Lamp"
import { Level } from "@/components/Level"
import { StateLabel } from "@/components/StateLabel"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useTickets } from "@/hooks/queries"
import { ago, money } from "@/lib/format"
import { STATES } from "@/lib/status"
import { cn } from "@/lib/utils"
import type { Ticket, TicketState } from "@/lib/api"

function Th({ icon: Icon, color, children, className }: { icon: LucideIcon; color: string; children: string; className?: string }) {
  return (
    <TableHead className={className}>
      <span className="inline-flex items-center gap-1.5">
        <Icon aria-hidden className={cn("size-3.5", color)} />
        {children}
      </span>
    </TableHead>
  )
}

const ALL = Object.keys(STATES) as TicketState[]

const RISKS = ["low", "medium", "high"]

type Option<T> = { value: T; label: string; count: number; icon?: ReactNode }

function FilterRow<T extends string>({ label, options, selected, onChange }: { label: string; options: Option<T>[]; selected: Set<T>; onChange: (s: Set<T>) => void }) {
  if (options.length === 0) return null
  const toggle = (v: T) => {
    const next = new Set(selected)
    if (!next.delete(v)) next.add(v)
    onChange(next)
  }
  return (
    <div className="flex flex-wrap items-center gap-1.5 md:shrink-0 md:flex-nowrap" role="group" aria-label={`Filter by ${label.toLowerCase()}`}>
      <span className="text-xs font-medium uppercase tracking-[0.06em] text-muted-foreground">{label}</span>
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => toggle(o.value)}
          aria-pressed={selected.has(o.value)}
          className={cn("inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-[13px] hover:bg-muted", selected.has(o.value) && "border-primary bg-accent text-accent-foreground")}
        >
          {o.icon}{o.label} <span className="tabular-nums text-muted-foreground">{o.count}</span>
        </button>
      ))}
    </div>
  )
}

const tint = (s: TicketState, pct: number) => `color-mix(in oklab, var(--lamp-${STATES[s].lamp}) ${pct}%, transparent)`

export function Tickets() {
  const { data, isLoading } = useTickets()
  const [q, setQ] = useState("")
  const [states, setStates] = useState<Set<TicketState>>(new Set())
  const [risks, setRisks] = useState<Set<string>>(new Set())
  const [areas, setAreas] = useState<Set<string>>(new Set())
  const [models, setModels] = useState<Set<string>>(new Set())
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()

  const tickets = data?.tickets ?? []
  const count = <K,>(key: (t: Ticket) => K | null) => {
    const c = new Map<K, number>()
    tickets.forEach((t) => { const k = key(t); if (k != null) c.set(k, (c.get(k) ?? 0) + 1) })
    return c
  }
  const stateCounts = count((t) => t.status)
  const riskCounts = count((t) => t.risk)
  const areaCounts = count((t) => t.area)
  const modelCounts = count((t) => t.model ?? "Auto")

  const needle = q.toLowerCase()
  const rows = tickets
    .filter(
      (t) =>
        (!states.size || states.has(t.status)) &&
        (!risks.size || (t.risk != null && risks.has(t.risk))) &&
        (!areas.size || (t.area != null && areas.has(t.area))) &&
        (!models.size || models.has(t.model ?? "Auto")) &&
        (!needle || [t.title, t.id, t.area, t.branch].some((v) => v?.toLowerCase().includes(needle))),
    )
    .sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""))
  const chips = states.size + risks.size + areas.size + models.size
  const active = chips + (q ? 1 : 0)
  const clear = () => { setQ(""); setStates(new Set()); setRisks(new Set()); setAreas(new Set()); setModels(new Set()) }

  return (
    <>
      <PageHeader title="Tickets">
        {data && `${active ? `${rows.length} of ` : ""}${tickets.length} ${tickets.length === 1 ? "ticket" : "tickets"}`}
      </PageHeader>

      <div className="mb-5 space-y-3">
        <div className="flex items-center gap-3">
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search title, id, area or branch" aria-label="Search tickets" className="min-w-0 flex-1 md:w-80 md:flex-none" />
          <button
            onClick={() => setOpen(!open)}
            aria-expanded={open}
            aria-controls="ticket-filters"
            className={cn("inline-flex h-9 shrink-0 items-center gap-1.5 rounded-md border bg-card px-3 text-sm hover:bg-muted md:hidden", chips > 0 && "border-primary bg-accent text-accent-foreground")}
          >
            <ListFilter className="size-4" />Filters
            {chips > 0 && <span className="grid min-w-5 place-items-center rounded-full bg-primary px-1 text-xs font-medium tabular-nums text-primary-foreground">{chips}</span>}
            <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} />
          </button>
          {active > 0 && (
            <button onClick={clear} className="hidden items-center gap-1 text-[13px] md:inline-flex text-muted-foreground hover:text-foreground">
              <X className="size-3.5" />Clear filters
            </button>
          )}
        </div>
        <div className={cn("grid transition-[grid-template-rows] duration-200 md:block", open ? "grid-rows-[1fr]" : "grid-rows-[0fr]")}>
          <div id="ticket-filters" className="flex min-h-0 flex-col gap-2 overflow-hidden md:flex-row md:items-center md:gap-x-5 md:overflow-x-auto md:pb-1">
            <FilterRow label="Status" selected={states} onChange={setStates} options={ALL.filter((s) => stateCounts.has(s)).map((s) => ({ value: s, label: STATES[s].label, count: stateCounts.get(s)!, icon: <Lamp kind={STATES[s].lamp} className="size-2" /> }))} />
            <FilterRow label="Risk" selected={risks} onChange={setRisks} options={RISKS.filter((r) => riskCounts.has(r)).map((r) => ({ value: r, label: r, count: riskCounts.get(r)! }))} />
            <FilterRow label="Area" selected={areas} onChange={setAreas} options={[...areaCounts].sort().map(([a, n]) => ({ value: a, label: a, count: n }))} />
            <FilterRow label="Model" selected={models} onChange={setModels} options={[...modelCounts].sort().map(([m, n]) => ({ value: m, label: m, count: n }))} />
            {active > 0 && (
              <button onClick={clear} className="inline-flex items-center gap-1 self-start text-[13px] text-muted-foreground hover:text-foreground md:hidden">
                <X className="size-3.5" />Clear filters
              </button>
            )}
          </div>
        </div>
      </div>

      {isLoading && <Skeleton className="h-64 w-full" />}
      {data && rows.length === 0 && <p className="py-6 text-muted-foreground">{data.tickets.length === 0 ? "No tickets yet." : "No ticket matches your search or filter."}</p>}
      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-sm border">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent select-none">
                <Th icon={Activity} color="text-lamp-green">Status</Th>
                <Th icon={Type} color="text-lamp-blue">Title</Th>
                <Th icon={Folder} color="text-lamp-amber">Area</Th>
                <Th icon={ShieldAlert} color="text-lamp-red">Risk</Th>
                <Th icon={Cpu} color="text-lamp-violet">Model</Th>
                <Th icon={RotateCw} color="text-lamp-blue" className="text-right">Attempts</Th>
                <Th icon={Coins} color="text-lamp-amber" className="text-right">Cost</Th>
                <Th icon={Clock} color="text-lamp-green">Updated</Th>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((t) => (
                <TableRow
                  key={t.id}
                  tabIndex={0}
                  role="link"
                  onClick={() => navigate(`/tickets/${t.id}`)}
                  onKeyDown={(e) => e.key === "Enter" && navigate(`/tickets/${t.id}`)}
                  className="ticket-row h-14 cursor-pointer hover:bg-transparent"
                >
                  <TableCell>
                    <span className="inline-flex rounded-full px-2.5 py-1 text-[13px] font-medium" style={{ backgroundColor: tint(t.status, 18) }}>
                      <StateLabel state={t.status} />
                    </span>
                  </TableCell>
                  <TableCell className="max-w-md truncate font-medium">{t.title}</TableCell>
                  <TableCell>
                    {t.area ? <span className="rounded-sm bg-muted px-2 py-0.5 font-mono text-[12px]">{t.area}</span> : "—"}
                  </TableCell>
                  <TableCell>{t.risk ? <span className="inline-flex items-center gap-2"><Level value={t.risk} /></span> : "—"}</TableCell>
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
