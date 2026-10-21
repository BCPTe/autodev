import { useEffect, useState } from "react"
import { Hand, OctagonX } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useOverview } from "@/hooks/queries"
import { useAct } from "@/hooks/useAct"
import { put, post, type Mode } from "@/lib/api"
import { cn } from "@/lib/utils"

export const MODES: { id: Mode; label: string; hint: string }[] = [
  { id: "auto", label: "Auto", hint: "Analizza, approva i ticket a rischio consentito e li lavora da solo" },
  { id: "supervised", label: "Supervisionato", hint: "Analizza e lavora da solo, ma sei tu ad approvare il passaggio in lavorazione" },
  { id: "manual", label: "Manuale", hint: "Non parte niente finché non premi Avvia" },
  { id: "paused", label: "In pausa", hint: "Non parte niente; i lavori in corso finiscono, oppure fermali" },
]

export function ModeSwitch() {
  const { data } = useOverview()
  const { act, pending } = useAct()
  if (!data) return null
  const mode = data.control.mode
  return (
    <div role="radiogroup" aria-label="Autonomia" className="flex overflow-hidden rounded-md border">
      {MODES.map((m) => (
        <button
          key={m.id}
          role="radio"
          aria-checked={mode === m.id}
          title={m.hint}
          disabled={pending}
          onClick={() => mode !== m.id && act(() => put("/api/control", { mode: m.id }), `Modalità: ${m.label}`)}
          className={cn(
            "px-3 py-1.5 text-[13px] transition-colors not-last:border-r",
            mode === m.id
              ? m.id === "paused" ? "bg-lamp-amber/25 font-medium text-foreground" : "bg-primary font-medium text-primary-foreground"
              : "text-muted-foreground hover:bg-muted hover:text-foreground",
          )}
        >
          {m.label}
        </button>
      ))}
    </div>
  )
}

export function MyTurn() {
  const { data } = useOverview()
  const { act, pending } = useAct()
  if (!data) return null
  const on = data.control.my_turn
  return (
    <Button
      variant={on ? "default" : "outline"}
      size="sm"
      disabled={pending}
      aria-pressed={on}
      title={on ? "Stai lavorando nel checkout: gli agenti aspettano. Premi per restituirlo" : "Prendi il checkout: finché non lo restituisci nessun agente parte"}
      onClick={() => act(() => put("/api/control", { my_turn: !on }), on ? "Checkout restituito agli agenti" : "Il checkout è tuo")}
    >
      <Hand /> {on ? "Turno tuo" : "Il mio turno"}
    </Button>
  )
}

/** Two clicks: the first arms the button, the second stops every running agent. */
export function StopAll() {
  const { data } = useOverview()
  const { act, pending } = useAct()
  const [armed, setArmed] = useState(false)
  useEffect(() => {
    if (!armed) return
    const t = setTimeout(() => setArmed(false), 4000)
    return () => clearTimeout(t)
  }, [armed])
  if (!data || data.running.length === 0) return null
  return (
    <Button
      variant="destructive"
      size="sm"
      disabled={pending}
      onClick={() => (armed ? (setArmed(false), act(() => post("/api/control/stop-all", {}), "Agenti fermati")) : setArmed(true))}
    >
      <OctagonX /> {armed ? "Conferma: ferma tutto" : "Ferma tutto"}
    </Button>
  )
}

export function Notice() {
  const { data } = useOverview()
  const c = data?.control
  if (!c) return null
  const lines = [
    c.blocked && `Automazione ferma: ${c.blocked}`,
    c.my_turn && "È il tuo turno: nessun agente parte finché non restituisci il checkout.",
    c.mode === "paused" && "Modalità in pausa: nessun agente parte.",
    c.quiet && c.mode !== "paused" && `Ore di silenzio (${c.quiet_hours}): niente parte da solo, ma puoi avviare a mano.`,
  ].filter(Boolean) as string[]
  if (!lines.length) return null
  return (
    <div role="status" className="border-b border-lamp-amber/40 bg-lamp-amber/15 px-4 py-2 text-[13px] sm:px-6">
      {lines.map((l) => <p key={l}>{l}</p>)}
    </div>
  )
}
