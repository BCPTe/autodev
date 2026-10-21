import { useEffect, useState } from "react"
import { Hand, OctagonX } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useOverview } from "@/hooks/queries"
import { useAct } from "@/hooks/useAct"
import { put, post, type Mode } from "@/lib/api"
import { cn } from "@/lib/utils"

export const MODES: { id: Mode; label: string; hint: string }[] = [
  { id: "auto", label: "Auto", hint: "Analyses, approves tickets of an allowed risk level and works on them by itself" },
  { id: "supervised", label: "Supervised", hint: "Analyses and works by itself, but you approve moving a ticket to In progress" },
  { id: "manual", label: "Manual", hint: "Nothing starts until you press Start" },
  { id: "paused", label: "Paused", hint: "Nothing starts; running jobs finish, or stop them" },
]

export function ModeSwitch() {
  const { data } = useOverview()
  const { act, pending } = useAct()
  if (!data) return null
  const mode = data.control.mode
  return (
    <div role="radiogroup" aria-label="Autonomy" className="flex overflow-hidden rounded-md border">
      {MODES.map((m) => (
        <button
          key={m.id}
          role="radio"
          aria-checked={mode === m.id}
          title={m.hint}
          disabled={pending}
          onClick={() => mode !== m.id && act(() => put("/api/control", { mode: m.id }), `Mode: ${m.label}`)}
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
      title={on ? "You are working in the checkout: agents wait. Press to hand it back" : "Take the checkout: no agent starts until you hand it back"}
      onClick={() => act(() => put("/api/control", { my_turn: !on }), on ? "Checkout handed back to the agents" : "The checkout is yours")}
    >
      <Hand /> {on ? "Checkout is yours" : "Take checkout"}
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
      onClick={() => (armed ? (setArmed(false), act(() => post("/api/control/stop-all", {}), "Agents stopped")) : setArmed(true))}
    >
      <OctagonX /> {armed ? "Confirm: stop all" : "Stop all"}
    </Button>
  )
}

export function Notice() {
  const { data } = useOverview()
  const c = data?.control
  if (!c) return null
  const lines = [
    c.blocked && `Automation is stopped: ${c.blocked}`,
    c.my_turn && "The checkout is yours: no agent starts until you hand it back.",
    c.mode === "paused" && "Paused mode: no agent starts.",
    c.quiet && c.mode !== "paused" && `Quiet hours (${c.quiet_hours}): nothing starts by itself, but you can start things by hand.`,
  ].filter(Boolean) as string[]
  if (!lines.length) return null
  return (
    <div role="status" className="border-b border-lamp-amber/40 bg-lamp-amber/15 px-4 py-2 text-[13px] sm:px-6">
      {lines.map((l) => <p key={l}>{l}</p>)}
    </div>
  )
}
