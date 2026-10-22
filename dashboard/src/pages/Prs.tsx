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
  open: { label: "Open", lamp: "green" },
  merged: { label: "Merged", lamp: "violet" },
  closed: { label: "Closed", lamp: "idle" },
}
const CHECKS = { none: "No checks on GitHub", unknown: "Checks unreadable (token permissions)", passing: "Checks passed", failing: "Checks failed", pending: "Checks running" } as const

function mergeBlocker(p: Pr): string | null {
  if (p.draft) return "It is a draft"
  if (p.checks?.verdict === "failing") return "The checks on GitHub failed"
  if (p.checks?.verdict === "unknown") return "Checks cannot be read with this token: merge on GitHub, or give the token 'Checks' and 'Commit statuses' (read)"
  if (p.checks?.verdict === "pending") return "The checks on GitHub are still running"
  if (p.mergeable === false) return "There are conflicts with the base branch"
  if (p.ticket?.risk === "High") return "High risk: merge it by hand on GitHub after reading it"
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
          <div className="flex items-center gap-2"><Lamp kind={p.checks.verdict === "passing" ? "green" : p.checks.verdict === "failing" ? "red" : p.checks.verdict === "pending" || p.checks.verdict === "unknown" ? "amber" : "idle"} className="size-2" />{CHECKS[p.checks.verdict]}</div>
        )}
        {p.ticket && <div>Risk {p.ticket.risk ?? "—"}</div>}
        {p.ticket?.verification && <div>autodev verification: {p.ticket.verification}</div>}
        {p.mergeable === false && <div className="text-destructive">Conflicts</div>}
      </dl>

      {p.body && (
        <div className="ml-5">
          <button className="text-[13px] text-primary underline-offset-4 hover:underline" aria-expanded={open} onClick={() => setOpen(!open)}>
            {open ? "Hide the description" : "Show the description and the evidence"}
          </button>
          {open && <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap rounded-sm border bg-card p-3 font-sans text-[13px] leading-relaxed">{p.body}</pre>}
        </div>
      )}

      <div className="ml-5 flex flex-wrap items-center gap-2">
        <Button asChild size="sm" variant="outline"><a href={p.url} target="_blank" rel="noreferrer">Open on GitHub <ExternalLink /></a></Button>
        {p.state === "open" && (
          <Button
            size="sm"
            disabled={pending || !!blocker}
            title={blocker ?? undefined}
            onClick={() => (armed ? (setArmed(false), act(() => post(`/api/prs/${p.number}/merge`, { confirm: true }), "Pull request merged")) : (setArmed(true), setTimeout(() => setArmed(false), 4000)))}
          >
            <GitMerge /> {armed ? "Confirm: squash and merge" : "Merge"}
          </Button>
        )}
        {blocker && <span className="text-[13px] font-medium text-foreground">Merge is disabled: {blocker}</span>}
      </div>
    </li>
  )
}

export function Prs() {
  const { data, isLoading, error } = usePrs()
  return (
    <>
      <PageHeader title="Pull request">The ones opened by autodev. Merging always needs your confirmation and is not possible for High risk.</PageHeader>
      {isLoading && <Skeleton className="h-48 w-full" />}
      {error && <p role="alert" className="text-destructive">{(error as Error).message}</p>}
      {data && data.prs.length === 0 && <p className="py-6 text-muted-foreground">No pull requests. They appear when a verified fix is published (<span className="font-mono">pr.create</span> attivo).</p>}
      {data && <ul className="divide-y border-y">{data.prs.map((p) => <PrRow key={p.number} p={p} />)}</ul>}
    </>
  )
}
