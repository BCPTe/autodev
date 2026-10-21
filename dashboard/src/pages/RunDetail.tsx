import { Link, useParams, useSearchParams } from "react-router-dom"
import { ExternalLink } from "lucide-react"
import { Lamp } from "@/components/Lamp"
import { RunFeed } from "@/components/RunFeed"
import { Skeleton } from "@/components/ui/skeleton"
import { useRun } from "@/hooks/queries"
import { useNow } from "@/hooks/useNow"
import { ago, duration, money, shortModel } from "@/lib/format"
import { KIND_LABEL, RUN_LABEL, RUN_LAMP } from "@/lib/status"

export function RunDetail() {
  const id = Number(useParams().id)
  const { data, isError } = useRun(id)
  const [, setParams] = useSearchParams()
  const now = useNow(1000)
  if (isError) return <p className="text-destructive">Esecuzione non trovata. <Link className="underline" to="/runs">Torna all'elenco</Link></p>
  if (!data) return <Skeleton className="h-64 w-full" />
  const r = data.run
  const elapsed = r.status === "running" ? now / 1000 - r.started_at : r.duration

  return (
    <>
      <p className="mb-2 text-sm"><Link className="text-muted-foreground underline-offset-4 hover:underline" to="/runs">Esecuzioni</Link></p>
      <div className="mb-6">
        <h1 className="text-3xl font-semibold">{KIND_LABEL[r.kind]}: {r.ticket_title}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1 text-sm">
          <span className="inline-flex items-center gap-2"><Lamp kind={RUN_LAMP[r.status]} live={r.status === "running"} />{RUN_LABEL[r.status]}{r.outcome ? ` · ${r.outcome}` : ""}</span>
          <span className="text-muted-foreground">{shortModel(r.model)}</span>
          <span className="tabular-nums text-muted-foreground">{duration(elapsed)}</span>
          <span className="tabular-nums text-muted-foreground">{money(r.cost_usd)}</span>
          <span className="text-muted-foreground">avviato {ago(r.started_at)}</span>
          <button className="text-primary underline-offset-4 hover:underline" onClick={() => setParams({ ticket: r.ticket_id })}>Apri il ticket</button>
          {r.pr_url && <a className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline" href={r.pr_url} target="_blank" rel="noreferrer">Pull request <ExternalLink className="size-3.5" /></a>}
        </div>
        {r.branch && <p className="mt-2 font-mono text-[13px]">{r.branch}</p>}
        {r.error && <p role="alert" className="mt-3 whitespace-pre-wrap rounded-sm border-l-2 border-destructive bg-muted/60 p-3 text-[13px]">{r.error}</p>}
      </div>
      <RunFeed runId={id} className="h-[60vh]" />
    </>
  )
}
