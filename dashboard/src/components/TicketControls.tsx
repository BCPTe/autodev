import { useState } from "react"
import { GitPullRequest, Lightbulb, Play, RotateCcw, ShieldCheck, X } from "lucide-react"
import { MergeBranchButton } from "@/components/NeedsYouCards"
import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { useConfig, useOverview } from "@/hooks/queries"
import { useAct } from "@/hooks/useAct"
import { patch, post, type Ticket, type TicketState } from "@/lib/api"

const selectClass = "h-8 rounded-md border bg-background px-2 text-sm"

/** Why a job cannot start right now, or null. Mirrors the server's checks so the button can say it. */
function blockedReason(c: { mode: string; my_turn: boolean; busy: boolean } | undefined): string | null {
  if (!c) return "Caricamento..."
  if (c.mode === "paused") return "Paused mode"
  if (c.my_turn) return "The checkout is yours"
  if (c.busy) return "An agent is already working"
  return null
}

/** Close or reopen: an action on the ticket as a whole, not a step of its flow. */
export function CloseTicket({ ticket: t }: { ticket: Ticket }) {
  const { act, pending } = useAct()
  const setStatus = (status: TicketState, done: string) => act(() => patch(`/api/tickets/${t.id}`, { status }), done)
  if (t.status === "closed") return <Button size="sm" variant="outline" disabled={pending} onClick={() => setStatus("new", "Reopened")} leftIcon={<RotateCcw />}>Reopen</Button>
  return (
    <Button
      size="sm"
      variant="outline"
      color="red"
      disabled={pending}
      onClick={() => setStatus("closed", "Closed")}
      leftIcon={<X />}
    >
      Close ticket
    </Button>
  )
}

export function TicketControls({ ticket: t }: { ticket: Ticket }) {
  const { act, pending } = useAct()
  const { data: overview } = useOverview()
  const { data: config } = useConfig()
  const blocked = blockedReason(overview?.control)
  const state: TicketState = t.status

  const setStatus = (status: TicketState, done: string, extra: object = {}) =>
    act(() => patch(`/api/tickets/${t.id}`, { status, ...extra }), done)
  const start = (kind: "triage" | "fix" | "publish" | "learn", done: string) => act(() => post(`/api/tickets/${t.id}/start`, { kind }), done)
  const approveAndStart = async () => {
    if (await setStatus("in_progress", "Approved")) await start("fix", "Fix started")
  }

  const startBtn = (kind: "triage" | "fix", label: string, variant: "default" | "secondary" = "secondary") => (
    <Button size="sm" variant={variant} disabled={pending || !!blocked} title={blocked ?? undefined} onClick={() => start(kind, kind === "fix" ? "Fix started" : "Triage started")} leftIcon={<Play />}>{label}</Button>
  )

  // after a verified fix whose pull request could not be opened, publishing is the move; retrying the agent is the fallback
  const canOpenPr = state === "escalated" && !!config?.pr_enabled && !t.pr_url && !!t.branch && t.verification === "Passed"

  return (
    <section aria-label="Actions" className="space-y-3 pt-3">
      <div className="flex flex-wrap items-center gap-2">
        {state === "new" && startBtn("triage", "Analyse now", "default")}
        {state === "needs_info" && (
          <>
            {/* answering happens in the comment box, which also restarts the triage; this is for answers left on Notion */}
            {startBtn("triage", "Analyse again", "default")}
          </>
        )}
        {state === "analyzed" && (
          <>
            <Button size="sm" disabled={pending || !!blocked} title={blocked ?? undefined} onClick={approveAndStart} leftIcon={<ShieldCheck />}>Approve and start</Button>
            <Button size="sm" variant="secondary" disabled={pending} onClick={() => setStatus("in_progress", "Approved")}>Approve only</Button>
            {startBtn("triage", "Analyse again")}
          </>
        )}
        {state === "in_progress" && startBtn("fix", "Start fix", "default")}
        {state === "review" && (
          <>
          <MergeBranchButton ticket={t} />
          <Button size="sm" variant="secondary" disabled={pending} onClick={() => setStatus("in_progress", "Moved back to In progress")} leftIcon={<RotateCcw />}>Move back to In progress</Button>
          </>
        )}
        {/* only after a verified fix whose pull request could not be opened (see pipeline._fix_in_workspace) */}
        {canOpenPr && (
          <Button
            size="sm"
            disabled={pending || !!blocked}
            title={blocked ?? "Opens the pull request for the work already done on the branch (re-runs the checks, no agent)"}
            onClick={() => start("publish", "Opening the pull request")}
            leftIcon={<GitPullRequest />}
          >
            Open PR
          </Button>
        )}
        {state === "escalated" && (
          <Button size="sm" variant={canOpenPr ? "secondary" : "default"} disabled={pending} onClick={() => setStatus("in_progress", "Ready to run again: attempts reset", { attempts: 0 })} leftIcon={<RotateCcw />}>Retry (reset attempts)</Button>
        )}
        {blocked && (state === "new" || state === "in_progress") && <span className="text-xs text-muted-foreground">{blocked}</span>}
      </div>

      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
        <label className="inline-flex items-center gap-2">
          <input
            type="checkbox"
            className="size-4 accent-primary"
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
          <ConfirmDialog
            trigger={<Button size="sm" color="red" disabled={pending}>Reset attempts ({t.attempts})</Button>}
            title="Reset attempts?"
            description={`This sets the ${t.attempts} recorded attempt(s) on this ticket back to 0.`}
            confirmLabel="Reset attempts"
            color="red"
            onConfirm={() => act(() => patch(`/api/tickets/${t.id}`, { attempts: 0 }), "Attempts reset")}
          />
        )}
        {(state === "closed" || state === "review") && (
          <Button
            className="ml-auto"
            size="sm"
            color="amber"
            disabled={pending || !!blocked}
            title={blocked ?? "A cheap read-only agent reads how this ticket went and proposes playbook entries for you to review"}
            onClick={() => start("learn", "Retrospective started: proposals will appear in Learnings")}
            leftIcon={<Lightbulb />}
          >
            Learn from this ticket
          </Button>
        )}
      </div>
    </section>
  )
}

/**
 * Comment box. With `reanalyse` (the triage asked questions, or got the problem wrong) sending is the whole
 * answer: the comment goes to the ticket and the triage starts again.
 */
export function CommentBox({ ticketId, reanalyse = false }: { ticketId: string; reanalyse?: boolean }) {
  const { act, pending } = useAct()
  const [text, setText] = useState("")
  const send = async () => {
    if (!reanalyse) {
      if (await act(() => post(`/api/tickets/${ticketId}/comment`, { text }), "Comment sent to Notion")) setText("")
      return
    }
    if (!(await act(() => post(`/api/tickets/${ticketId}/comment`, { text })))) return
    setText("")
    // if no agent can start now (one is busy, Paused mode...) the answer is saved and the error says why
    await act(() => post(`/api/tickets/${ticketId}/start`, { kind: "triage" }), "Answer sent: autodev is analysing the ticket again")
  }
  return (
    <form className="mt-3 space-y-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) send() }}>
      <label htmlFor="new-comment" className="sr-only">New comment</label>
      <textarea
        id="new-comment"
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={3}
        placeholder={reanalyse
          ? "Answer its questions or correct what it understood: autodev reads it and analyses the ticket again"
          : "Add context: it goes into the ticket's comments on Notion and the agent reads it"}
        className="w-full resize-y rounded-md border bg-background px-3 py-2 text-[13.5px]"
      />
      <Button type="submit" size="sm" loading={pending} disabled={!text.trim()}>{reanalyse ? "Send and analyse again" : "Send comment"}</Button>
    </form>
  )
}

export const ACTION_LABEL: Record<string, string> = {
  start_triage: "started the triage",
  start_fix: "started the fix",
  start_learn: "started the retrospective",
  approve: "approved",
  edit: "edited the ticket",
  comment: "commented",
  stop: "stopped an agent",
  message: "wrote to the agent",
  approval: "answered a request from the agent",
}
