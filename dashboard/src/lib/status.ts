import type { Run, TicketState } from "@/lib/api"

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
  needs_info: { label: "Needs info", lamp: "amber", owner: "you", hint: "Answer with a comment and move it back to New" },
  analyzed: { label: "Analysed", lamp: "blue", owner: "you", hint: "Read the analysis; if it looks right, approve it" },
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
export const KIND_LABEL: Record<Run["kind"], string> = { triage: "Triage", fix: "Fix", checks: "Checks" }
