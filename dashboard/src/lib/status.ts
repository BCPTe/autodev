import type { Run, TicketState } from "@/lib/api"

export type Lamp = "idle" | "amber" | "green" | "red" | "violet" | "blue"

interface StateMeta {
  label: string
  lamp: Lamp
  /** who has to act on a ticket in this state */
  owner: "tu" | "autodev" | "nessuno"
  hint: string
}

export const STATES: Record<TicketState, StateMeta> = {
  new: { label: "Nuovo", lamp: "idle", owner: "autodev", hint: "In attesa di triage" },
  needs_info: { label: "Serve info", lamp: "amber", owner: "tu", hint: "Rispondi con un commento e riportalo in Nuovo" },
  analyzed: { label: "Analizzato", lamp: "blue", owner: "tu", hint: "Leggi l'analisi: se va bene passalo in lavorazione" },
  in_progress: { label: "In lavorazione", lamp: "violet", owner: "autodev", hint: "L'agente lavora o aspetta di partire" },
  review: { label: "Da rivedere", lamp: "green", owner: "tu", hint: "Prova il fix e fai merge della PR" },
  escalated: { label: "Escalation umana", lamp: "red", owner: "tu", hint: "Guarda le note dell'agente e decidi" },
  closed: { label: "Chiuso", lamp: "idle", owner: "nessuno", hint: "" },
}

/** Stations on the pipeline rail, left to right. needs_info and escalated sit off the main track. */
export const TRACK: TicketState[] = ["new", "analyzed", "in_progress", "review", "closed"]
export const OFF_TRACK: TicketState[] = ["needs_info", "escalated"]

export const RUN_LAMP: Record<Run["status"], Lamp> = { running: "violet", done: "green", failed: "red", cancelled: "amber" }
export const RUN_LABEL: Record<Run["status"], string> = { running: "In corso", done: "Finito", failed: "Fallito", cancelled: "Interrotto" }
export const KIND_LABEL: Record<Run["kind"], string> = { triage: "Triage", fix: "Fix", checks: "Controlli" }
