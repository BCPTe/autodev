import { useRef, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { ArrowLeft, ArrowUpRight, Bot, Check, ChevronRight, ExternalLink, Info, MessageSquareWarning } from "lucide-react"
import { ApprovalCard } from "@/components/ApprovalCard"
import { Attachments } from "@/components/Attachments"
import { DiffView } from "@/components/DiffView"
import { Lamp } from "@/components/Lamp"
import { PushPanel } from "@/components/PushPanel"
import { RunFeed } from "@/components/RunFeed"
import { Level } from "@/components/Level"
import { StateLabel } from "@/components/StateLabel"
import { StopRun } from "@/components/StopRun"
import { ACTION_LABEL, CloseTicket, CommentBox, TicketControls } from "@/components/TicketControls"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useConfig, useOverview, usePrs, usePushPlan, useTicket } from "@/hooks/queries"
import { type Comment, type Run, type Ticket, type TicketAction } from "@/lib/api"
import { ago, duration, money, shortModel } from "@/lib/format"
import { fixPhase, JOURNEY, journeyStep, KIND_LABEL, RUN_LABEL, RUN_LAMP, STATES } from "@/lib/status"
import { latestUnderstanding, type Understanding } from "@/lib/understanding"
import { cn } from "@/lib/utils"
import { PrRow } from "@/pages/Prs"

function Journey({ ticket, runs }: { ticket: Ticket; runs: Run[] }) {
  const step = journeyStep(ticket.status, { fix: runs.some((r) => r.kind === "fix"), pr: !!ticket.pr_url })
  const stuck = ticket.status === "needs_info" || ticket.status === "escalated"
  return (
    <ol className="grid grid-cols-3 gap-y-3 sm:grid-cols-6" aria-label="Ticket progress">
      {JOURNEY.map((s, i) => {
        const done = i < step || ticket.status === "closed"
        const current = i === step && ticket.status !== "closed"
        return (
          <li key={s.key} aria-current={current ? "step" : undefined} className="relative flex flex-col items-center gap-1.5 text-center">
            {i > 0 && <span aria-hidden className={cn("absolute right-1/2 top-[9px] hidden h-px w-full sm:block", i <= step ? "bg-primary" : "bg-rail")} />}
            <span className={cn(
              "relative z-10 grid size-[18px] place-items-center rounded-full bg-background ring-1 ring-rail",
              done && "bg-primary ring-primary text-primary-foreground",
              current && (stuck ? "ring-2 ring-lamp-amber" : "ring-2 ring-primary"),
            )}>
              {done ? <Check className="size-3" strokeWidth={3} /> : current && <span className={cn("size-2 rounded-full", stuck ? "bg-lamp-amber" : "bg-primary")} />}
            </span>
            <span className={cn("text-[13px]", current ? "font-semibold" : done ? "" : "text-muted-foreground")}>{s.label}</span>
          </li>
        )
      })}
    </ol>
  )
}

/** Who has to act now and how: the one place a person looks to move the ticket on. */
function NextStep({ ticket, runs }: { ticket: Ticket; runs: Run[] }) {
  const { data: overview } = useOverview()
  const { data: config } = useConfig()
  // the ticket whose branch was last merged on this machine is where the push is offered (only without pull requests)
  const mergedHere = ticket.status === "closed" && !ticket.pr_url && config?.pr_enabled === false
  const { data: push } = usePushPlan(mergedHere)
  const pushing = mergedHere && !!push?.can_push && push.ticket_id === ticket.id
  const meta = STATES[ticket.status]
  const ahead = overview?.running.find((r) => r.ticket_id !== ticket.id)
  const phase = ticket.status === "in_progress" ? fixPhase(runs, overview?.control) : null
  const yours = meta.owner === "you" || pushing
  // with pull requests off nothing is pushed: the fix lives on a local branch and the user pushes after merging it
  const localOnly = ticket.status === "review" && !ticket.pr_url
  const hint = localOnly
    ? `The fix is on the local branch ${ticket.branch ?? ""} and nothing was pushed. Try it, merge it from the Repo page, then push ${ticket.branch ? "the base branch" : "it"} yourself.`
    : meta.hint
  return (
    <section aria-labelledby="next-step" className={cn("rounded-lg border p-4", yours ? "border-primary/50 bg-accent/30" : "bg-card")}>
      <h2 id="next-step" className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {yours ? "Your move" : meta.owner === "autodev" ? "autodev's move" : "Done"}
      </h2>
      <p className="mb-3 text-[15px] font-medium">{pushing ? <>Merged on your computer<span className="block text-[13px] font-normal text-muted-foreground">It is not on origin yet. Push it when you are ready.</span></> : phase ? <>{phase.title}<span className="block text-[13px] font-normal text-muted-foreground">{phase.hint}</span></> : hint || "Nothing left to do."}</p>
      {phase?.key === "queued" && ahead && (
        <Link to={`/tickets/${ahead.ticket_id}`} className="mb-3 flex items-center gap-2.5 rounded-md border border-lamp-violet/40 bg-background/60 px-3 py-2 text-[13px] transition-colors hover:border-primary/60">
          <Lamp kind="violet" live />
          <span className="min-w-0 flex-1">
            <span className="block text-xs text-muted-foreground">In front of it: {KIND_LABEL[ahead.kind].toLowerCase()} on {ahead.ticket_id}</span>
            <span className="block truncate font-medium">{ahead.ticket_title || ahead.ticket_id}</span>
          </span>
          {/* Elapsed time since a server timestamp: a one-off read at render is enough. */}
          {/* oxlint-disable-next-line react/purity */}
          <span className="shrink-0 text-xs tabular-nums text-muted-foreground">{duration(Date.now() / 1000 - ahead.started_at)}</span>
          <ArrowUpRight className="size-4 shrink-0 text-primary" aria-hidden />
        </Link>
      )}
      {pushing ? <PushPanel quiet /> : <TicketControls ticket={ticket} />}
    </section>
  )
}

/** The triage's restatement of the problem, for the requester to confirm before any fix starts. */
function UnderstandingCard({ ticket, u, onCorrect }: { ticket: Ticket; u: Understanding; onCorrect: () => void }) {
  const open = ticket.status === "analyzed" || ticket.status === "needs_info"
  const rows = [["Where", u.where], ["Expected", u.expected], ["What happens instead", u.actual]] as const
  // open while the requester still has to confirm it, folded away once the work has moved on
  const [expanded, setExpanded] = useState(open || u.questions.length > 0)
  return (
    <section aria-labelledby="understood" className="rounded-lg border bg-card/60 backdrop-blur-sm p-4">
      <h2 id="understood">
        <button className="flex w-full items-baseline gap-3 text-left" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
          <ChevronRight className={cn("size-4 shrink-0 self-center transition-transform", expanded && "rotate-90")} aria-hidden />
          <span className="text-lg font-semibold">What autodev understood</span>
          <span className="text-xs text-muted-foreground">{ago(u.at)}</span>
        </button>
      </h2>
      {expanded && <div className="mt-3">
      {(u.expected || u.actual) && (
        <dl className="space-y-2.5 text-[14px]">
          {rows.filter(([, v]) => v).map(([label, v]) => (
            <div key={label} className="grid gap-x-4 sm:grid-cols-[9rem_1fr]">
              <dt className="text-muted-foreground">{label}</dt>
              <dd>{v}</dd>
            </div>
          ))}
          {u.steps.length > 0 && (
            <div className="grid gap-x-4 sm:grid-cols-[9rem_1fr]">
              <dt className="text-muted-foreground">Steps</dt>
              <dd><ol className="list-decimal space-y-0.5 pl-5">{u.steps.map((s, i) => <li key={i}>{s}</li>)}</ol></dd>
            </div>
          )}
        </dl>
      )}
      {u.questions.length > 0 && (
        <div className="mt-4 rounded-md border border-lamp-amber/60 bg-lamp-amber/10 p-3">
          <p className="mb-1.5 flex items-center gap-2 font-medium"><MessageSquareWarning className="size-4 text-lamp-amber" aria-hidden /> It needs an answer before it can go on</p>
          <ul className="list-disc space-y-1 pl-5 text-[14px]">{u.questions.map((q, i) => <li key={i}>{q}</li>)}</ul>
        </div>
      )}
      {open && (
        <div className="mt-4 border-t pt-4">
          <Button size="sm" variant="outline" onClick={onCorrect}>{u.questions.length ? "Answer" : "Not quite: correct it"}</Button>
        </div>
      )}
      </div>}
    </section>
  )
}

type Entry =
  | { at: number; kind: "comment"; c: Comment }
  | { at: number; kind: "run"; r: Run }
  | { at: number; kind: "action"; a: TicketAction }

function timeline(comments: Comment[], runs: Run[], actions: TicketAction[]): Entry[] {
  const entries: Entry[] = [
    ...comments.map((c) => ({ at: c.created_at ? Date.parse(c.created_at) / 1000 : 0, kind: "comment" as const, c })),
    ...runs.map((r) => ({ at: r.started_at, kind: "run" as const, r })),
    // starting a run is already shown by the run itself
    ...actions.filter((a) => !a.action.startsWith("start_") && a.action !== "comment").map((a) => ({ at: a.ts, kind: "action" as const, a })),
  ]
  return entries.sort((a, b) => a.at - b.at)
}

/** Round marker beside a message: who is speaking. */
function Avatar({ bot, name }: { bot: boolean; name: string }) {
  return (
    <span aria-hidden className={cn("mt-5 grid size-7 shrink-0 place-items-center rounded-full text-xs font-semibold", bot ? "bg-lamp-violet/15 text-lamp-violet" : "bg-primary/15 text-primary")}>
      {bot ? <Bot className="size-4" /> : name.trim().charAt(0).toUpperCase() || "?"}
    </span>
  )
}

/** One chat message: people on the right, autodev and its agents on the left, each with a name and a time. */
function Message({ bot, name, at, children }: { bot: boolean; name: string; at: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className={cn("flex gap-2.5", !bot && "flex-row-reverse")}>
      <Avatar bot={bot} name={name} />
      <div className={cn("flex min-w-0 max-w-[85%] flex-col gap-1", !bot && "items-end")}>
        <div className="flex items-baseline gap-2 px-1 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">{name}</span>
          <span>{at}</span>
        </div>
        {children}
      </div>
    </div>
  )
}

/** A comment clamped to a few lines; a click opens it in full and folds it again. */
function CommentEntry({ c }: { c: Comment }) {
  const [full, setFull] = useState(false)
  const [clamped, setClamped] = useState(false)
  const measure = (el: HTMLParagraphElement | null) => {
    if (el && !full) setClamped(el.scrollHeight > el.clientHeight + 1)
  }
  return (
    <Message bot={c.is_bot} name={c.author || (c.is_bot ? "autodev" : "Someone")} at={ago(c.created_at)}>
      <div
        className={cn(
          "rounded-2xl border px-3.5 py-2.5",
          c.is_bot ? "rounded-tl-sm bg-card" : "rounded-tr-sm border-primary/30 bg-accent/40",
          clamped && "cursor-pointer hover:border-primary/50",
        )}
        onClick={() => clamped && !window.getSelection()?.toString() && setFull(!full)}
      >
        <p ref={measure} className={cn("whitespace-pre-wrap text-[13.5px] leading-relaxed", !full && "line-clamp-4")}>{c.text}</p>
        {clamped && (
          <button className="mt-1 text-xs font-medium text-primary" aria-expanded={full} onClick={(ev) => { ev.stopPropagation(); setFull(!full) }}>
            {full ? "Show less" : "Show more"}
          </button>
        )}
      </div>
    </Message>
  )
}

function Timeline({ entries }: { entries: Entry[] }) {
  if (!entries.length) return <p className="text-muted-foreground">Nothing has happened yet.</p>
  return (
    <ol className="space-y-4">
      {entries.map((e, i) => (
        <li key={i}>
          {e.kind === "comment" && <CommentEntry c={e.c} />}
          {e.kind === "run" && (
            <Message bot name={`autodev · ${KIND_LABEL[e.r.kind]}`} at={ago(e.r.started_at)}>
              <Link
                to={`/runs/${e.r.id}`}
                title="Open this run in Activity"
                className="group flex flex-wrap items-center gap-x-3 gap-y-0.5 rounded-2xl rounded-tl-sm border border-lamp-violet/30 bg-card px-3.5 py-2 text-[13px] transition-colors hover:border-primary/60 hover:bg-accent/40"
              >
                <Lamp kind={RUN_LAMP[e.r.status]} live={e.r.status === "running"} className="size-2.5" />
                <span className="font-medium">{RUN_LABEL[e.r.status]}{e.r.outcome ? `: ${e.r.outcome}` : ""}</span>
                <span className="text-muted-foreground">{shortModel(e.r.model)} · {duration(e.r.duration)} · {money(e.r.cost_usd)}</span>
                <span className="ml-auto inline-flex items-center gap-0.5 text-xs font-medium text-primary">
                  View run <ArrowUpRight className="size-3.5 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" aria-hidden />
                </span>
              </Link>
              {e.r.error && <p className="px-1 text-[13px] text-destructive">{e.r.error}</p>}
            </Message>
          )}
          {e.kind === "action" && (
            <p className="text-center text-xs text-muted-foreground">
              <span className="font-medium text-foreground">{e.a.actor === "auto" ? "Automatic" : "You"}</span> {ACTION_LABEL[e.a.action] ?? e.a.action}
              {e.a.action === "approve" && e.a.detail ? ` (${e.a.detail})` : ""} · {ago(e.a.ts)}
            </p>
          )}
        </li>
      ))}
    </ol>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="flex min-w-0 items-center justify-end gap-2 truncate text-right">{children || "—"}</dd>
    </div>
  )
}

/** Fix attempts as dots out of the limit, red once the limit is reached. */
function Attempts({ used, max }: { used: number; max?: number }) {
  if (!max) return used
  return (
    <>
      <span className="tabular-nums">{used}/{max}</span>
      <span aria-hidden className="flex gap-1">
        {Array.from({ length: max }, (_, j) => (
          <span key={j} className={cn("size-2 rounded-full", j < used ? (used >= max ? "bg-lamp-red" : "bg-primary") : "bg-rail")} />
        ))}
      </span>
    </>
  )
}

/** Spend against the per-ticket budget as a bar that warms as it fills. */
function Budget({ spent, budget }: { spent: number; budget?: number }) {
  if (!budget) return money(spent)
  const share = Math.min(spent / budget, 1)
  return (
    <span className="flex w-36 flex-col items-end gap-1">
      <span className="tabular-nums"><span className="font-medium">{money(spent)}</span> <span className="text-muted-foreground">of {money(budget)}</span></span>
      <span aria-hidden className="h-1.5 w-full overflow-hidden rounded-full bg-rail">
        <span className={cn("block h-full rounded-full", share >= 0.9 ? "bg-lamp-red" : share >= 0.6 ? "bg-lamp-amber" : "bg-lamp-green")} style={{ width: `${share * 100}%` }} />
      </span>
    </span>
  )
}

function Verification({ value }: { value: string | null }) {
  if (!value) return null
  const v = value.toLowerCase()
  const tone = v.startsWith("pass") ? "green" : v.startsWith("fail") ? "red" : "amber"
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium",
      { green: "bg-lamp-green/15 text-lamp-green", red: "bg-lamp-red/15 text-lamp-red", amber: "bg-lamp-amber/15 text-lamp-amber" }[tone])}>
      <Lamp kind={tone} className="size-1.5" /> {value}
    </span>
  )
}

/** The ticket's bookkeeping, kept out of the way behind an info icon beside the title. */
function DetailsInfo({ ticket: t }: { ticket: Ticket }) {
  const { data: config } = useConfig()
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button aria-label="Ticket details" className="mt-2 shrink-0 rounded-full text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring">
          <Info className="size-5" />
        </button>
      </TooltipTrigger>
      <TooltipContent side="bottom" align="start" sideOffset={6} className="w-80 border bg-popover p-3 text-[13px] text-popover-foreground shadow-md [&>span]:hidden">
        <dl className="divide-y">
          <Field label="Area">{t.area && <span className="rounded-sm bg-muted px-1.5 py-0.5 text-xs font-medium">{t.area}</span>}</Field>
          <Field label="Priority"><Level value={t.priority} /></Field>
          <Field label="Risk"><Level value={t.risk} /></Field>
          <Field label="Model"><span className="rounded-sm bg-lamp-violet/15 px-1.5 py-0.5 text-xs font-medium text-lamp-violet">{t.model ? shortModel(t.model) : "Auto"}</span></Field>
          <Field label="Fix attempts"><Attempts used={t.attempts} max={config?.limits.max_attempts} /></Field>
          <Field label="Spent"><Budget spent={t.cost_usd} budget={config?.limits.budget_usd_per_ticket} /></Field>
          <Field label="Verification"><Verification value={t.verification} /></Field>
          <Field label="Branch">{t.branch && <span className="truncate font-mono text-xs">{t.branch}</span>}</Field>
          <Field label="Updated">{ago(t.updated_at)}</Field>
        </dl>
        {t.url && (
          <a href={t.url} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline">
            Open in Notion <ExternalLink className="size-3.5" />
          </a>
        )}
      </TooltipContent>
    </Tooltip>
  )
}

/** The agent working on this ticket now, as a live feed beside the decisions. */
function LiveRun({ run: r }: { run: Run }) {
  return (
    <section aria-label="Agent at work" className="rounded-lg border border-lamp-violet/40 bg-card p-3">
      <header className="mb-2 flex flex-wrap items-center gap-x-2.5 gap-y-1">
        <Lamp kind="violet" live />
        <Link to={`/runs/${r.id}`} className="font-medium underline-offset-4 hover:underline">{KIND_LABEL[r.kind]} running</Link>
        <span className="text-[13px] text-muted-foreground">{shortModel(r.model)}</span>
        <span className="ml-auto"><StopRun run={r} /></span>
      </header>
      <RunFeed runId={r.id} className="h-[min(36rem,65vh)]" />
    </section>
  )
}

/** Everything about one ticket, in the order it happens: where it is, what is needed now, and its history. */
export function TicketPage() {
  const { id = null } = useParams()
  const { data, isLoading, error } = useTicket(id)
  const { data: overview } = useOverview()
  const { data: prs } = usePrs()
  const [showDiff, setShowDiff] = useState<boolean | null>(null)
  const commentRef = useRef<HTMLDivElement>(null)

  if (isLoading) return <div className="space-y-4"><Skeleton className="h-10 w-2/3" /><Skeleton className="h-24 w-full" /><Skeleton className="h-64 w-full" /></div>
  if (error || !data) return <p role="alert" className="text-destructive">Could not read the ticket: {(error as Error | null)?.message ?? "not found"}</p>

  const t = data.ticket
  const runIds = new Set(data.runs.map((r) => r.id))
  const approvals = overview?.approvals.filter((a) => runIds.has(a.run_id)) ?? []
  const running = data.runs.filter((r) => r.status === "running")
  const pr = prs?.prs.find((p) => p.ticket?.id === t.id || (t.branch && p.branch === t.branch))
  const understanding = latestUnderstanding(data.comments)
  // the diff is reviewed in the merge dialog; here it stays folded until asked for
  const diffOpen = showDiff ?? false
  const result = (pr || t.branch) && (
    <section aria-labelledby="result" className="space-y-3">
      <h2 id="result" className="text-lg font-semibold">Result</h2>
      {pr && <ul className="divide-y border-y"><PrRow p={pr} bare /></ul>}
      {t.branch && (
        <div>
          <button className="flex items-center gap-1 text-[14px] font-medium" aria-expanded={diffOpen} onClick={() => setShowDiff(!diffOpen)}>
            <ChevronRight className={cn("size-4 transition-transform", diffOpen && "rotate-90")} aria-hidden /> Changes on <span className="font-mono text-xs">{t.branch}</span>
          </button>
          {diffOpen && <div className="mt-2"><DiffView branch={t.branch} /></div>}
        </div>
      )}
    </section>
  )
  const toComment = () => {
    commentRef.current?.scrollIntoView({ behavior: "smooth", block: "center" })
    commentRef.current?.querySelector("textarea")?.focus()
  }

  return (
    <>
      <Link to="/tickets" className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" /> All tickets</Link>
      <header className="mb-6">
        <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
          <div className="flex min-w-0 items-start gap-2">
            <h1 className="min-w-0 text-3xl font-semibold leading-tight tracking-[-0.01em]">{t.title}</h1>
            <DetailsInfo ticket={t} />
          </div>
          <CloseTicket ticket={t} />
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
          <StateLabel state={t.status} />
          {t.reported_by && <span>Reported by {t.reported_by}</span>}
          {t.created_at && <span>Opened {ago(t.created_at)}</span>}
        </div>
      </header>

      <div className="mb-8"><Journey ticket={t} runs={data.runs} /></div>

      {/* The record of the ticket on the left (description, result, history and the comment box);
          on the right, sticky, what needs a decision now and what the agent is doing. On narrow screens
          the decisions come first. */}
      <div className="grid gap-x-8 gap-y-8 lg:grid-cols-[minmax(0,1fr)_minmax(26rem,0.8fr)]">
        <aside className="min-w-0 space-y-4 lg:sticky lg:top-6 lg:col-start-2 lg:row-start-1 lg:self-start">
          {approvals.map((a) => <ApprovalCard key={a.id} a={a} showRun={false} />)}
          <NextStep ticket={t} runs={data.runs} />
          {t.agent_note && (t.status === "escalated" || t.status === "needs_info") && (
            <p className="whitespace-pre-wrap rounded-md border border-lamp-amber/50 bg-lamp-amber/10 p-3 text-[13px] leading-relaxed">{t.agent_note}</p>
          )}
          {understanding && <UnderstandingCard ticket={t} u={understanding} onCorrect={toComment} />}
          {running.map((r) => <LiveRun key={r.id} run={r} />)}
        </aside>

        <div className="min-w-0 space-y-10 lg:col-start-1 lg:row-start-1">
          <section aria-labelledby="description">
            <h2 id="description" className="mb-2 text-lg font-semibold">Description</h2>
            <p className="max-w-[72ch] whitespace-pre-wrap text-[14px] leading-relaxed">{t.body || "No description."}</p>
          </section>

          <Attachments ticketId={t.id} />

          {result}

          <section aria-labelledby="history">
            <h2 id="history" className="mb-3 text-lg font-semibold">History</h2>
            <Timeline entries={timeline(data.comments, data.runs, data.actions)} />
            <div ref={commentRef}><CommentBox ticketId={t.id} reanalyse={t.status === "needs_info" || t.status === "analyzed"} /></div>
          </section>
        </div>
      </div>
    </>
  )
}
