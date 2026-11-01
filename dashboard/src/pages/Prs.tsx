import { useState } from "react"
import { Check, Clock, ExternalLink, GitMerge, X } from "lucide-react"
import { PageHeader } from "@/components/PageHeader"
import { Lamp } from "@/components/Lamp"
import { Level } from "@/components/Level"
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
const CHECKS = { none: "No checks on GitHub", unknown: "Checks could not be read", passing: "Checks passed", failing: "Checks failed", pending: "Checks running" } as const

export function mergeBlocker(p: Pr): string | null {
  if (p.draft) return "The pull request is still a draft"
  if (p.checks?.verdict === "failing") return "GitHub checks failed"
  if (p.checks?.verdict === "unknown") return `GitHub checks could not be read: ${p.checks.reason ?? "check the token permissions"}`
  if (p.checks?.verdict === "pending") return "GitHub checks are still running"
  if (p.mergeable === false) return "It conflicts with the base branch"
  if (p.ticket?.risk === "High") return "High risk: read it and merge by hand on GitHub"
  return null
}

/** "3 of 4 checks passed" with an icon for the verdict; the plain verdict when there is nothing to count. */
function ChecksSummary({ c }: { c: NonNullable<Pr["checks"]> }) {
  if (c.verdict === "none" || c.verdict === "unknown" || !c.total)
    return <div className="flex items-center gap-2"><Lamp kind={c.verdict === "unknown" ? "amber" : "idle"} className="size-2" />{CHECKS[c.verdict]}</div>
  const passed = Math.max(0, c.total - c.failed - c.pending)
  const [Icon, tone] = c.failed ? [X, "text-lamp-red"] : c.pending ? [Clock, "text-lamp-amber"] : [Check, "text-lamp-green"]
  return <div className="flex items-center gap-1.5"><Icon className={`size-4 ${tone}`} strokeWidth={2.5} aria-hidden />{passed} of {c.total} checks passed{c.failed > 0 && `, ${c.failed} failed`}{c.pending > 0 && `, ${c.pending} running`}</div>
}

/** Squash merge behind a confirming second click, with the reason when it cannot be merged. */
export function MergePrButton({ p }: { p: Pr }) {
  const { act, pending } = useAct()
  const [armed, setArmed] = useState(false)
  const blocker = mergeBlocker(p)
  return (
    <>
      <Button
        size="sm"
        disabled={pending || !!blocker}
        title={blocker ?? undefined}
        onClick={() => (armed ? (setArmed(false), act(() => post(`/api/prs/${p.number}/merge`, { confirm: true }), (r) => ((r as { back_on?: string | null }).back_on ? `Pull request merged; checkout back on ${(r as { back_on: string }).back_on}` : "Pull request merged"))) : (setArmed(true), setTimeout(() => setArmed(false), 4000)))}
        leftIcon={<GitMerge />}
      >
        {armed ? "Confirm: squash and merge" : "Merge"}
      </Button>
      {blocker && <span className="text-[13px] font-medium text-foreground">Merge unavailable: {blocker}</span>}
    </>
  )
}

/** `bare` leaves out the action row, for a page that offers the actions elsewhere. */
export function PrRow({ p, bare = false }: { p: Pr; bare?: boolean }) {
  const [open, setOpen] = useState(false)

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
        {p.checks && <ChecksSummary c={p.checks} />}
        {p.checks?.note && <div className="text-muted-foreground">{p.checks.note}</div>}
        {p.ticket && <div className="flex items-center gap-1.5">Risk <Level value={p.ticket.risk} /></div>}
        {p.ticket?.verification && <div>autodev verification: {p.ticket.verification}</div>}
        {p.mergeable === false && <div className="text-destructive">Conflicts</div>}
      </dl>

      {p.body && (
        <div className="ml-5">
          <button className="text-[13px] text-primary underline-offset-4 hover:underline" aria-expanded={open} onClick={() => setOpen(!open)}>
            {open ? "Hide description" : "Show description and evidence"}
          </button>
          {open && <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap rounded-sm border bg-card p-3 font-sans text-[13px] leading-relaxed">{p.body}</pre>}
        </div>
      )}

      {!bare && <div className="ml-5 flex flex-wrap items-center gap-2">
        <Button asChild size="sm" variant="outline"><a href={p.url} target="_blank" rel="noreferrer">Open on GitHub <ExternalLink /></a></Button>
        {p.state === "open" && <MergePrButton p={p} />}
      </div>}
    </li>
  )
}

export function Prs() {
  const { data, isLoading, error } = usePrs()
  return (
    <>
      <PageHeader title="Pull requests">Opened by autodev. Merging always asks you to confirm; High-risk pull requests must be merged by hand on GitHub.</PageHeader>
      {isLoading && <Skeleton className="h-48 w-full" />}
      {error && <p role="alert" className="text-destructive">{(error as Error).message}</p>}
      {data && data.prs.length === 0 && <p className="py-6 text-muted-foreground">No pull requests yet. One appears here when autodev publishes a verified fix (requires <span className="font-mono">pr.create</span> to be on).</p>}
      {data && <ul className="divide-y border-y">{data.prs.map((p) => <PrRow key={p.number} p={p} />)}</ul>}
    </>
  )
}
