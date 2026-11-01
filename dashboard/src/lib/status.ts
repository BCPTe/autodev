import type { Control, Run, TicketState } from "@/lib/api"

export type Lamp = "idle" | "amber" | "green" | "red" | "violet" | "blue"

interface StateMeta {
  label: string
  lamp: Lamp
  /** who has to act on a ticket in this state */
  owner: "you" | "autodev" | "nobody"
  hint: string
}

export const STATES: Record<TicketState, StateMeta> = {
  new: { label: "New", lamp: "idle", owner: "autodev", hint: "Waiting for triage" },
  needs_info: { label: "Needs info", lamp: "amber", owner: "you", hint: "Answer its questions below: autodev analyses the ticket again when you send" },
  analyzed: { label: "Analysed", lamp: "blue", owner: "you", hint: "Check what autodev understood: if it is right, approve it" },
  in_progress: { label: "In progress", lamp: "violet", owner: "autodev", hint: "The agent is working or about to start" },
  review: { label: "In review", lamp: "green", owner: "you", hint: "Try the fix and merge the PR" },
  escalated: { label: "Needs a human", lamp: "red", owner: "you", hint: "Read the agent's notes and decide" },
  closed: { label: "Closed", lamp: "idle", owner: "nobody", hint: "" },
}

/** Stations on the pipeline rail, left to right. needs_info and escalated sit off the main track. */
export const TRACK: TicketState[] = ["new", "analyzed", "in_progress", "review", "closed"]
export const OFF_TRACK: TicketState[] = ["needs_info", "escalated"]

export const RUN_LAMP: Record<Run["status"], Lamp> = { running: "violet", done: "green", failed: "red", cancelled: "amber" }
export const RUN_LABEL: Record<Run["status"], string> = { running: "Running", done: "Finished", failed: "Failed", cancelled: "Stopped" }
export const KIND_LABEL: Record<Run["kind"], string> = { triage: "Triage", fix: "Fix", checks: "Checks", publish: "Open PR", learn: "Retrospective" }

/** The ticket's journey as the person reads it: one step per thing that has to happen, in order. */
export const JOURNEY = [
  { key: "received", label: "Received" },
  { key: "understood", label: "Understood" },
  { key: "approved", label: "Approved" },
  { key: "fixing", label: "Fixing" },
  { key: "review", label: "Review" },
  { key: "closed", label: "Closed" },
] as const

/** Index of the step a ticket is on; needs_info is stuck before "Understood", escalated wherever it stopped. */
export function journeyStep(state: TicketState, hasRuns: { fix: boolean; pr: boolean }): number {
  switch (state) {
    case "new": return 0
    case "needs_info": return 1
    case "analyzed": return 2
    case "in_progress": return 3
    case "review": return 4
    case "closed": return 5
    case "escalated": return hasRuns.pr ? 4 : hasRuns.fix ? 3 : 1
  }
}

export interface Phase {
  key: "running" | "queued" | "stopped" | "retry" | "ready"
  title: string
  hint: string
}

/** What "In progress" really means right now: the state alone cannot tell a running agent from a ticket waiting its turn. */
export function fixPhase(runs: Run[], c: Control | undefined): Phase {
  if (runs.some((r) => r.status === "running")) return { key: "running", title: "Fixing", hint: "An agent is working on it now" }
  if (c?.mode === "paused") return { key: "stopped", title: "On hold", hint: "The mode is Paused: switch it to Auto, Supervised or Manual so the fix can start" }
  if (c?.my_turn) return { key: "stopped", title: "On hold", hint: "The checkout is yours: hand it back so the fix can start" }
  if (c?.busy) return { key: "queued", title: "In the queue", hint: "Only one agent runs at a time: the fix starts when the current one finishes" }
  if (c?.blocked) return { key: "stopped", title: "On hold", hint: `Blocked: ${c.blocked}` }
  const last = runs.filter((r) => r.kind === "fix").sort((a, b) => b.started_at - a.started_at)[0]
  if (last && (last.status === "failed" || last.status === "cancelled"))
    return { key: "retry", title: "Last fix did not finish", hint: last.error ? `${RUN_LABEL[last.status]}: ${last.error}` : "Start it again or reset the attempts" }
  const auto = c?.mode === "auto" || c?.mode === "supervised"
  return { key: "ready", title: "Ready to fix", hint: auto ? "autodev starts it on its next check, or start it now" : "Start the fix when you are ready" }
}
