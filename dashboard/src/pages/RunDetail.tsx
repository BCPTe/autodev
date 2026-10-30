import { Link, useParams } from "react-router-dom"
import { ExternalLink } from "lucide-react"
import { Lamp } from "@/components/Lamp"
import { RunConsole } from "@/components/RunConsole"
import { RunFeed } from "@/components/RunFeed"
import { StopRun } from "@/components/StopRun"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useRun } from "@/hooks/queries"
import { useNow } from "@/hooks/useNow"
import { ago, duration, money, shortModel, tokens } from "@/lib/format"
import { KIND_LABEL, RUN_LABEL, RUN_LAMP } from "@/lib/status"
import { cn } from "@/lib/utils"

export function RunDetail() {
  const id = Number(useParams().id)
  const { data, isError } = useRun(id)
  const now = useNow(1000)
  if (isError) return <p className="text-destructive">Run not found. <Link className="underline" to="/runs">Back to Activity</Link></p>
  if (!data) return <Skeleton className="h-64 w-full" />
  const r = data.run
  const elapsed = r.status === "running" ? now / 1000 - r.started_at : r.duration

  return (
    <>
      <p className="mb-2 text-sm"><Link className="text-muted-foreground underline-offset-4 hover:underline" to="/runs">Activity</Link></p>
      <div className="mb-6">
        <h1 className="text-3xl font-semibold">{KIND_LABEL[r.kind]}: <Link to={`/tickets/${r.ticket_id}`} className="underline-offset-4 hover:underline">{r.ticket_title}</Link></h1>
        <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1 text-sm">
          <span className="inline-flex items-center gap-2"><Lamp kind={RUN_LAMP[r.status]} live={r.status === "running"} />{RUN_LABEL[r.status]}{r.outcome ? ` · ${r.outcome}` : ""}</span>
          <span className="text-muted-foreground">{shortModel(r.model)}</span>
          <span className="tabular-nums text-muted-foreground">{duration(elapsed)}</span>
          <span className="tabular-nums text-muted-foreground">{money(r.cost_usd)}</span>
          <span className="text-muted-foreground">started {ago(r.started_at)}</span>
          <StopRun run={r} />
          {r.kind !== "checks" && <Link className="text-primary underline-offset-4 hover:underline" to={`/tickets/${r.ticket_id}`}>Open ticket</Link>}
          {r.pr_url && <a className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline" href={r.pr_url} target="_blank" rel="noreferrer">Pull request <ExternalLink className="size-3.5" /></a>}
        </div>
        {r.branch && <p className="mt-2 font-mono text-[13px]">{r.branch}</p>}
        {r.error && <p role="alert" className="mt-3 whitespace-pre-wrap rounded-sm border-l-2 border-destructive bg-muted/60 p-3 text-[13px]">{r.error}</p>}
      </div>
      {r.sessions && r.sessions.length > 0 && (
        <section className="mb-6">
          <h2 className="mb-2 text-lg font-semibold">Sessions</h2>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Stage</TableHead><TableHead>Model</TableHead><TableHead className="text-right">Turns</TableHead>
                <TableHead className="text-right">Peak context</TableHead><TableHead className="text-right">Out</TableHead><TableHead className="text-right">Cache read</TableHead><TableHead className="text-right">Cache write</TableHead>
                <TableHead>Tools</TableHead><TableHead className="text-right">Cost</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {r.sessions.map((s, i) => (
                <TableRow key={i}>
                  <TableCell>{KIND_LABEL[s.stage as keyof typeof KIND_LABEL] ?? s.stage}{s.resumed ? " (resumed)" : ""}</TableCell>
                  <TableCell>{shortModel(s.model)}</TableCell>
                  <TableCell className="text-right tabular-nums">{s.turns}</TableCell>
                  <TableCell className={cn("text-right tabular-nums", s.peak_context > 100000 && "text-lamp-red")}>{s.peak_context ? tokens(s.peak_context) : "—"}</TableCell>
                  <TableCell className="text-right tabular-nums">{tokens(s.output)}</TableCell>
                  <TableCell className="text-right tabular-nums">{tokens(s.cache_read)}</TableCell>
                  <TableCell className="text-right tabular-nums">{tokens(s.cache_write)}</TableCell>
                  <TableCell className="text-[13px] text-muted-foreground">{Object.entries(s.tools).map(([t, n]) => `${t} ${n}`).join(" · ")}{s.denials ? ` · ${s.denials} denied` : ""}</TableCell>
                  <TableCell className="text-right tabular-nums">{money(s.cost_usd)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </section>
      )}
      <RunFeed runId={id} className="h-[55vh]" />
      {r.status === "running" && <RunConsole runId={id} interactive={data.interactive} />}
    </>
  )
}
