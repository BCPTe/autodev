import { useState } from "react"
import { ExternalLink, GitMerge } from "lucide-react"
import { PageHeader } from "@/components/PageHeader"
import { Lamp } from "@/components/Lamp"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { usePrs } from "@/hooks/queries"
import { useAct } from "@/hooks/useAct"
import { post, type Pr } from "@/lib/api"
import { ago } from "@/lib/format"
import type { Lamp as LampKind } from "@/lib/status"

const STATE: Record<Pr["state"], { label: string; lamp: LampKind }> = {
  open: { label: "Aperta", lamp: "green" },
  merged: { label: "Unita", lamp: "violet" },
  closed: { label: "Chiusa", lamp: "idle" },
}
const CHECKS = { none: "Nessun controllo su GitHub", passing: "Controlli passati", failing: "Controlli falliti", pending: "Controlli in corso" } as const

function mergeBlocker(p: Pr): string | null {
  if (p.draft) return "È una bozza"
  if (p.checks?.verdict === "failing") return "I controlli su GitHub sono falliti"
  if (p.checks?.verdict === "pending") return "I controlli su GitHub sono ancora in corso"
  if (p.mergeable === false) return "Ci sono conflitti con il branch di base"
  if (p.ticket?.risk === "Alto") return "Rischio Alto: unisci a mano su GitHub dopo averla letta"
  return null
}

function PrRow({ p }: { p: Pr }) {
  const { act, pending } = useAct()
  const [armed, setArmed] = useState(false)
  const [open, setOpen] = useState(false)
  const blocker = p.state === "open" ? mergeBlocker(p) : null

  return (
    <li className="space-y-2 py-4">
      <div className="flex flex-wrap items-start gap-x-4 gap-y-1">
        <Lamp kind={STATE[p.state].lamp} className="mt-1.5" />
        <div className="min-w-0 flex-1">
          <p className="font-medium">{p.title}</p>
          <p className="font-mono text-xs text-muted-foreground">#{p.number} · {p.branch} · {ago(p.updated_at)}</p>
        </div>
        <span className="text-[13px] text-muted-foreground">{STATE[p.state].label}</span>
      </div>

      <dl className="ml-5 flex flex-wrap gap-x-6 gap-y-1 text-[13px]">
        {p.checks && (
          <div className="flex items-center gap-2"><Lamp kind={p.checks.verdict === "passing" ? "green" : p.checks.verdict === "failing" ? "red" : p.checks.verdict === "pending" ? "amber" : "idle"} className="size-2" />{CHECKS[p.checks.verdict]}</div>
        )}
        {p.ticket && <div>Rischio {p.ticket.risk ?? "—"}</div>}
        {p.ticket?.verification && <div>Verifica di autodev: {p.ticket.verification}</div>}
        {p.mergeable === false && <div className="text-destructive">Conflitti</div>}
      </dl>

      {p.body && (
        <div className="ml-5">
          <button className="text-[13px] text-primary underline-offset-4 hover:underline" aria-expanded={open} onClick={() => setOpen(!open)}>
            {open ? "Nascondi la descrizione" : "Mostra la descrizione e le prove"}
          </button>
          {open && <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap rounded-sm border bg-card p-3 font-sans text-[13px] leading-relaxed">{p.body}</pre>}
        </div>
      )}

      <div className="ml-5 flex flex-wrap items-center gap-2">
        <Button asChild size="sm" variant="outline"><a href={p.url} target="_blank" rel="noreferrer">Apri su GitHub <ExternalLink /></a></Button>
        {p.state === "open" && (
          <Button
            size="sm"
            disabled={pending || !!blocker}
            title={blocker ?? undefined}
            onClick={() => (armed ? (setArmed(false), act(() => post(`/api/prs/${p.number}/merge`, { confirm: true }), "Pull request unita")) : (setArmed(true), setTimeout(() => setArmed(false), 4000)))}
          >
            <GitMerge /> {armed ? "Conferma: unisci in squash" : "Unisci"}
          </Button>
        )}
        {blocker && <span className="text-xs text-muted-foreground">{blocker}</span>}
      </div>
    </li>
  )
}

export function Prs() {
  const { data, isLoading, error } = usePrs()
  return (
    <>
      <PageHeader title="Pull request">Quelle aperte da autodev. L'unione è sempre una tua conferma e non è possibile per il rischio Alto.</PageHeader>
      {isLoading && <Skeleton className="h-48 w-full" />}
      {error && <p role="alert" className="text-destructive">{(error as Error).message}</p>}
      {data && data.prs.length === 0 && <p className="py-6 text-muted-foreground">Nessuna pull request. Compaiono quando un fix verificato viene pubblicato (<span className="font-mono">pr.create</span> attivo).</p>}
      {data && <ul className="divide-y border-y">{data.prs.map((p) => <PrRow key={p.number} p={p} />)}</ul>}
    </>
  )
}
