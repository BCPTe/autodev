import { useSearchParams } from "react-router-dom"
import type { Ticket, TicketState } from "@/lib/api"
import { OFF_TRACK, STATES, TRACK } from "@/lib/status"
import { cn } from "@/lib/utils"
import { Lamp } from "@/components/Lamp"

const MAX_CHIPS = 4

function Chips({ tickets }: { tickets: Ticket[] }) {
  const [, setParams] = useSearchParams()
  const open = (id: string) => setParams((p) => { const n = new URLSearchParams(p); n.set("ticket", id); return n })
  return (
    <ul className="mt-3 space-y-1">
      {tickets.slice(0, MAX_CHIPS).map((t) => (
        <li key={t.id}>
          <button
            onClick={() => open(t.id)}
            title={t.title}
            className="block w-full truncate rounded-sm border border-transparent bg-card px-2 py-1 text-left text-[13px] leading-snug shadow-[inset_0_0_0_1px_var(--border)] hover:shadow-[inset_0_0_0_1px_var(--ring)]"
          >
            {t.title}
          </button>
        </li>
      ))}
      {tickets.length > MAX_CHIPS && <li className="px-2 text-xs text-muted-foreground">+{tickets.length - MAX_CHIPS} altri</li>}
    </ul>
  )
}

/** The pipeline as a track: one station per state, tickets stand on the station they are in. */
export function PipelineRail({ tickets }: { tickets: Ticket[] }) {
  const by = (s: TicketState) => tickets.filter((t) => t.status === s)

  return (
    <section aria-label="Pipeline dei ticket">
      <div className="relative grid grid-cols-2 gap-x-4 gap-y-8 sm:grid-cols-5">
        <div aria-hidden className="absolute left-[10%] right-[10%] top-[9px] hidden h-px bg-rail sm:block" />
        {TRACK.map((state) => {
          const list = by(state)
          const meta = STATES[state]
          const attention = meta.owner === "tu" && list.length > 0
          return (
            <div key={state} className="relative min-w-0">
              <div className="flex items-center gap-2 sm:justify-center">
                <span className={cn("relative z-10 grid size-[18px] place-items-center rounded-full bg-background ring-1 ring-rail", attention && "ring-2 ring-primary")}>
                  <Lamp kind={list.length ? meta.lamp : "idle"} live={state === "in_progress" && list.length > 0} />
                </span>
              </div>
              <div className="mt-2 flex items-baseline gap-2 sm:justify-center">
                <h3 className="text-base font-semibold">{meta.label}</h3>
                <span className="font-display text-xl tabular-nums text-muted-foreground">{list.length}</span>
              </div>
              <Chips tickets={list} />
            </div>
          )
        })}
      </div>

      <div className="mt-8 grid gap-4 border-t border-dashed pt-4 sm:grid-cols-2">
        {OFF_TRACK.map((state) => {
          const list = by(state)
          const meta = STATES[state]
          return (
            <div key={state} className="min-w-0">
              <div className="flex items-baseline gap-2">
                <Lamp kind={list.length ? meta.lamp : "idle"} className="translate-y-px" />
                <h3 className="text-base font-semibold">{meta.label}</h3>
                <span className="font-display text-xl tabular-nums text-muted-foreground">{list.length}</span>
                <span className="text-xs text-muted-foreground">fuori dal percorso</span>
              </div>
              <Chips tickets={list} />
            </div>
          )
        })}
      </div>
    </section>
  )
}
