import { useState } from "react"
import { Play, RotateCcw, ShieldCheck } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useConfig, useOverview } from "@/hooks/queries"
import { useAct } from "@/hooks/useAct"
import { patch, post, type Ticket, type TicketAction, type TicketState } from "@/lib/api"
import { ago } from "@/lib/format"

const selectClass = "h-8 rounded-md border bg-background px-2 text-sm"

/** Why a job cannot start right now, or null. Mirrors the server's checks so the button can say it. */
function blockedReason(c: { mode: string; my_turn: boolean; busy: boolean } | undefined): string | null {
  if (!c) return "Caricamento..."
  if (c.mode === "paused") return "Modalità in pausa"
  if (c.my_turn) return "È il tuo turno"
  if (c.busy) return "Un agente è già al lavoro"
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
  const start = (kind: "triage" | "fix", done: string) => act(() => post(`/api/tickets/${t.id}/start`, { kind }), done)
  const approveAndStart = async () => {
    if (await setStatus("in_progress", "Approvato")) await start("fix", "Fix avviato")
  }

  const startBtn = (kind: "triage" | "fix", label: string, variant: "default" | "outline" = "outline") => (
    <Button size="sm" variant={variant} disabled={pending || !!blocked} title={blocked ?? undefined} onClick={() => start(kind, kind === "fix" ? "Fix avviato" : "Triage avviato")}>
      <Play /> {label}
    </Button>
  )

  return (
    <section aria-label="Azioni" className="space-y-3 rounded-sm border bg-muted/40 p-3">
      <div className="flex flex-wrap items-center gap-2">
        {state === "new" && startBtn("triage", "Analizza ora", "default")}
        {state === "needs_info" && (
          <>
            <Button size="sm" disabled={pending} onClick={() => setStatus("new", "Riportato in Nuovo")}><RotateCcw /> Riporta in Nuovo</Button>
            {startBtn("triage", "Analizza di nuovo")}
          </>
        )}
        {state === "analyzed" && (
          <>
            <Button size="sm" disabled={pending || !!blocked} title={blocked ?? undefined} onClick={approveAndStart}><ShieldCheck /> Approva e avvia</Button>
            <Button size="sm" variant="outline" disabled={pending} onClick={() => setStatus("in_progress", "Approvato")}>Solo approva</Button>
            {startBtn("triage", "Analizza di nuovo")}
          </>
        )}
        {state === "in_progress" && startBtn("fix", "Avvia fix", "default")}
        {state === "review" && (
          <Button size="sm" variant="outline" disabled={pending} onClick={() => setStatus("in_progress", "Rimesso in lavorazione")}><RotateCcw /> Rimetti in lavorazione</Button>
        )}
        {state === "escalated" && (
          <Button size="sm" disabled={pending} onClick={() => setStatus("in_progress", "Pronto a ripartire: azzerati i tentativi", { attempts: 0 })}><RotateCcw /> Riprova (azzera tentativi)</Button>
        )}
        {state === "closed" ? (
          <Button size="sm" variant="outline" disabled={pending} onClick={() => setStatus("new", "Riaperto")}>Riapri</Button>
        ) : (
          <Button size="sm" variant="ghost" disabled={pending} onClick={() => setStatus("closed", "Chiuso")}>Chiudi</Button>
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
            onChange={(e) => act(() => patch(`/api/tickets/${t.id}`, { authorized: e.target.checked }), e.target.checked ? "Ticket autorizzato" : "Autorizzazione tolta")}
          />
          Autorizzato
        </label>
        <label className="inline-flex items-center gap-2">
          Modello
          <select
            className={selectClass}
            value={t.model ?? "Auto"}
            disabled={pending}
            onChange={(e) => act(() => patch(`/api/tickets/${t.id}`, { model: e.target.value }), `Modello: ${e.target.value}`)}
          >
            {["Auto", ...Object.keys(config?.model_choices ?? {})].map((m) => <option key={m}>{m}</option>)}
          </select>
        </label>
        {t.attempts > 0 && (
          <Button size="xs" variant="outline" disabled={pending} onClick={() => act(() => patch(`/api/tickets/${t.id}`, { attempts: 0 }), "Tentativi azzerati")}>
            Azzera tentativi ({t.attempts})
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
    if (await act(() => post(`/api/tickets/${ticketId}/comment`, { text }), "Commento inviato a Notion")) setText("")
  }
  return (
    <form className="mt-3 space-y-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) send() }}>
      <label htmlFor="new-comment" className="sr-only">Nuovo commento</label>
      <textarea
        id="new-comment"
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={3}
        placeholder="Rispondi alle domande o aggiungi contesto: finisce nei commenti del ticket su Notion e l'agente lo legge"
        className="w-full resize-y rounded-md border bg-background px-3 py-2 text-[13.5px]"
      />
      <Button type="submit" size="sm" disabled={pending || !text.trim()}>Invia commento</Button>
    </form>
  )
}

const ACTION_LABEL: Record<string, string> = {
  start_triage: "ha avviato il triage",
  start_fix: "ha avviato il fix",
  approve: "ha approvato",
  edit: "ha modificato il ticket",
  comment: "ha commentato",
  stop: "ha fermato un agente",
  message: "ha scritto all'agente",
  approval: "ha risposto a una richiesta dell'agente",
}

export function History({ actions }: { actions: TicketAction[] }) {
  if (!actions.length) return null
  return (
    <section>
      <h3 className="mb-2 text-base font-semibold">Chi ha deciso</h3>
      <ul className="space-y-1 text-[13px]">
        {actions.map((a, i) => (
          <li key={i} className="flex gap-2">
            <span className="font-medium">{a.actor === "auto" ? "Automatico" : "Tu"}</span>
            <span className="text-muted-foreground">{ACTION_LABEL[a.action] ?? a.action}{a.action === "approve" && a.detail ? ` (${a.detail})` : ""}</span>
            <span className="ml-auto whitespace-nowrap text-xs text-muted-foreground">{ago(a.ts)}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}
