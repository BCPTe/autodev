import { Link, useSearchParams } from "react-router-dom"
import { PageHeader } from "@/components/PageHeader"
import { PipelineRail } from "@/components/PipelineRail"
import { RunFeed } from "@/components/RunFeed"
import { Lamp } from "@/components/Lamp"
import { Skeleton } from "@/components/ui/skeleton"
import { useOverview, useRuns, useTickets } from "@/hooks/queries"
import { useNow } from "@/hooks/useNow"
import { ago, duration, money, shortModel } from "@/lib/format"
import { KIND_LABEL, RUN_LAMP, STATES } from "@/lib/status"
import type { Run, TicketState } from "@/lib/api"

const ORDER: TicketState[] = ["escalated", "review", "analyzed", "needs_info"]

function Elapsed({ run }: { run: Run }) {
  const now = useNow(1000)
  return <span className="tabular-nums">{duration(now / 1000 - run.started_at)}</span>
}

export function Now() {
  const { data: tickets } = useTickets()
  const { data: overview } = useOverview()
  const { data: runs } = useRuns()
  const [, setParams] = useSearchParams()
  const open = (id: string) => setParams((p) => { const n = new URLSearchParams(p); n.set("ticket", id); return n })

  const inbox = [...(overview?.inbox ?? [])].sort((a, b) => ORDER.indexOf(a.state) - ORDER.indexOf(b.state))
  const problems = overview?.recent_problems ?? []
  const last = runs?.runs.find((r) => r.status !== "running")

  return (
    <>
      <PageHeader title="Ora">{overview?.repo && <span>Repo su <span className="font-mono">{overview.repo.branch}</span>{overview.repo.clean ? "" : " · modifiche non committate"}</span>}</PageHeader>

      {tickets ? <PipelineRail tickets={tickets.tickets} /> : <Skeleton className="h-48 w-full" />}

      <div className="mt-12 grid gap-10 lg:grid-cols-2">
        <section aria-labelledby="da-te">
          <h2 id="da-te" className="mb-3 text-xl font-semibold">Da te</h2>
          {overview && inbox.length === 0 && problems.length === 0 && <p className="text-muted-foreground">Niente da decidere.</p>}
          <ul className="divide-y border-y">
            {problems.map((r) => (
              <li key={`run-${r.id}`}>
                <Link to={`/runs/${r.id}`} className="flex items-start gap-3 py-3 hover:bg-muted/50">
                  <Lamp kind={RUN_LAMP[r.status]} className="mt-1.5" />
                  <div className="min-w-0">
                    <p className="truncate font-medium">{KIND_LABEL[r.kind]} {r.status === "failed" ? "fallito" : "interrotto"}: {r.ticket_title}</p>
                    <p className="truncate text-[13px] text-muted-foreground">{r.error ?? "Apri il run per i dettagli"}</p>
                  </div>
                  <span className="ml-auto whitespace-nowrap text-xs text-muted-foreground">{ago(r.started_at)}</span>
                </Link>
              </li>
            ))}
            {inbox.map(({ ticket, state }) => (
              <li key={ticket.id}>
                <button onClick={() => open(ticket.id)} className="flex w-full items-start gap-3 py-3 text-left hover:bg-muted/50">
                  <Lamp kind={STATES[state].lamp} className="mt-1.5" />
                  <div className="min-w-0">
                    <p className="truncate font-medium">{ticket.title}</p>
                    <p className="truncate text-[13px] text-muted-foreground">{STATES[state].label}: {STATES[state].hint}</p>
                  </div>
                  <span className="ml-auto whitespace-nowrap text-xs text-muted-foreground">{ago(ticket.updated_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="in-esecuzione">
          <h2 id="in-esecuzione" className="mb-3 text-xl font-semibold">In esecuzione</h2>
          {overview && overview.running.length === 0 && (
            <div className="border-y py-3">
              <p className="text-muted-foreground">Nessun agente al lavoro.</p>
              {last && (
                <p className="mt-1 text-[13px]">
                  Ultimo run: <Link className="underline underline-offset-4" to={`/runs/${last.id}`}>{KIND_LABEL[last.kind]} su {last.ticket_title}</Link>
                  <span className="text-muted-foreground"> · {ago(last.finished_at ?? last.started_at)} · {money(last.cost_usd)}</span>
                </p>
              )}
            </div>
          )}
          <div className="space-y-6">
            {overview?.running.map((r) => (
              <article key={r.id}>
                <header className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1">
                  <Lamp kind="violet" live />
                  <Link to={`/runs/${r.id}`} className="font-medium underline-offset-4 hover:underline">{KIND_LABEL[r.kind]}: {r.ticket_title}</Link>
                  <span className="text-[13px] text-muted-foreground">{shortModel(r.model)} · <Elapsed run={r} /></span>
                </header>
                <RunFeed runId={r.id} className="h-80" />
              </article>
            ))}
          </div>
        </section>
      </div>
    </>
  )
}
