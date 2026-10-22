import { useState } from "react"
import { GitPullRequest, Play, RotateCcw, ShieldCheck } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useConfig, useOverview } from "@/hooks/queries"
import { useAct } from "@/hooks/useAct"
import { patch, post, type Ticket, type TicketAction, type TicketState } from "@/lib/api"
import { ago } from "@/lib/format"

const selectClass = "h-8 rounded-md border bg-background px-2 text-sm"

/** Why a job cannot start right now, or null. Mirrors the server's checks so the button can say it. */
function blockedReason(c: { mode: string; my_turn: boolean; busy: boolean } | undefined): string | null {
  if (!c) return "Caricamento..."
  if (c.mode === "paused") return "Paused mode"
  if (c.my_turn) return "The checkout is yours"
  if (c.busy) return "An agent is already working"
  return null
}

export function TicketControls({ ticket: t }: { ticket: Ticket }) {
  const { act, pending } = useAct()
  const { data: overview } = useOverview()
  const { data: config } = useConfig()
  const blocked = blockedReason(overview?.control)
  const state: TicketState = t.status

  const setStatus = (status: TicketState, done: string, extra: object = {}) =>
    act(() => patch(`/api/tickets/${t.id}`, { status, ...extra }), done)
  const start = (kind: "triage" | "fix" | "publish", done: string) => act(() => post(`/api/tickets/${t.id}/start`, { kind }), done)
  const approveAndStart = async () => {
    if (await setStatus("in_progress", "Approved")) await start("fix", "Fix started")
  }

  const startBtn = (kind: "triage" | "fix", label: string, variant: "default" | "outline" = "outline") => (
    <Button size="sm" variant={variant} disabled={pending || !!blocked} title={blocked ?? undefined} onClick={() => start(kind, kind === "fix" ? "Fix started" : "Triage started")}>
      <Play /> {label}
    </Button>
  )

  return (
    <section aria-label="Actions" className="space-y-3 rounded-sm border bg-muted/40 p-3">
      <div className="flex flex-wrap items-center gap-2">
        {state === "new" && startBtn("triage", "Analyse now", "default")}
        {state === "needs_info" && (
          <>
            <Button size="sm" disabled={pending} onClick={() => setStatus("new", "Moved back to New")}><RotateCcw /> Move back to New</Button>
            {startBtn("triage", "Analyse again")}
          </>
        )}
        {state === "analyzed" && (
          <>
            <Button size="sm" disabled={pending || !!blocked} title={blocked ?? undefined} onClick={approveAndStart}><ShieldCheck /> Approve and start</Button>
            <Button size="sm" variant="outline" disabled={pending} onClick={() => setStatus("in_progress", "Approved")}>Approve only</Button>
            {startBtn("triage", "Analyse again")}
          </>
        )}
        {state === "in_progress" && startBtn("fix", "Start fix", "default")}
        {state === "review" && (
          <Button size="sm" variant="outline" disabled={pending} onClick={() => setStatus("in_progress", "Moved back to In progress")}><RotateCcw /> Move back to In progress</Button>
        )}
        {state === "escalated" && (
          <Button size="sm" disabled={pending} onClick={() => setStatus("in_progress", "Ready to run again: attempts reset", { attempts: 0 })}><RotateCcw /> Retry (reset attempts)</Button>
        )}
        {(state === "in_progress" || state === "escalated") && !t.pr_url && (t.branch || t.attempts > 0) && (
          <Button
            size="sm"
            variant="outline"
            disabled={pending || !!blocked}
            title={blocked ?? "Opens the pull request for the work already done on the branch (re-runs the checks, no agent)"}
            onClick={() => start("publish", "Opening the pull request")}
          >
            <GitPullRequest /> Open PR
          </Button>
        )}
        {state === "closed" ? (
          <Button size="sm" variant="outline" disabled={pending} onClick={() => setStatus("new", "Reopened")}>Reopen</Button>
        ) : (
          <Button size="sm" variant="ghost" disabled={pending} onClick={() => setStatus("closed", "Closed")}>Close</Button>
        )}
        {blocked && (state === "new" || state === "in_progress") && <span className="text-xs text-muted-foreground">{blocked}</span>}
      </div>

      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
        <label className="inline-flex items-center gap-2">
          <input
            type="checkbox"
            className="size-4 accent-[var(--primary)]"
            checked={t.authorized}
            disabled={pending}
            onChange={(e) => act(() => patch(`/api/tickets/${t.id}`, { authorized: e.target.checked }), e.target.checked ? "Ticket authorised" : "Authorisation removed")}
          />
          Authorised
        </label>
        <label className="inline-flex items-center gap-2">
          Model
          <select
            className={selectClass}
            value={t.model ?? "Auto"}
            disabled={pending}
            onChange={(e) => act(() => patch(`/api/tickets/${t.id}`, { model: e.target.value }), `Model: ${e.target.value}`)}
          >
            {["Auto", ...Object.keys(config?.model_choices ?? {})].map((m) => <option key={m}>{m}</option>)}
          </select>
        </label>
        {t.attempts > 0 && (
          <Button size="xs" variant="outline" disabled={pending} onClick={() => act(() => patch(`/api/tickets/${t.id}`, { attempts: 0 }), "Attempts reset")}>
            Reset attempts ({t.attempts})
          </Button>
        )}
      </div>
    </section>
  )
}

export function CommentBox({ ticketId }: { ticketId: string }) {
  const { act, pending } = useAct()
  const [text, setText] = useState("")
  const send = async () => {
    if (await act(() => post(`/api/tickets/${ticketId}/comment`, { text }), "Comment sent to Notion")) setText("")
  }
  return (
    <form className="mt-3 space-y-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) send() }}>
      <label htmlFor="new-comment" className="sr-only">New comment</label>
      <textarea
        id="new-comment"
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={3}
        placeholder="Answer its questions or add context: it goes into the ticket's comments on Notion and the agent reads it"
        className="w-full resize-y rounded-md border bg-background px-3 py-2 text-[13.5px]"
      />
      <Button type="submit" size="sm" disabled={pending || !text.trim()}>Send comment</Button>
    </form>
  )
}

const ACTION_LABEL: Record<string, string> = {
  start_triage: "started the triage",
  start_fix: "started the fix",
  approve: "approved",
  edit: "edited the ticket",
  comment: "commented",
  stop: "stopped an agent",
  message: "wrote to the agent",
  approval: "answered a request from the agent",
}

export function History({ actions }: { actions: TicketAction[] }) {
  if (!actions.length) return null
  return (
    <section>
      <h3 className="mb-2 text-base font-semibold">Who decided</h3>
      <ul className="space-y-1 text-[13px]">
        {actions.map((a, i) => (
          <li key={i} className="flex gap-2">
            <span className="font-medium">{a.actor === "auto" ? "Automatic" : "You"}</span>
            <span className="text-muted-foreground">{ACTION_LABEL[a.action] ?? a.action}{a.action === "approve" && a.detail ? ` (${a.detail})` : ""}</span>
            <span className="ml-auto whitespace-nowrap text-xs text-muted-foreground">{ago(a.ts)}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}
