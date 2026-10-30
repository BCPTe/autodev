import { useNavigate } from "react-router-dom"
import type { Ticket, TicketState } from "@/lib/api"
import { STATES, TRACK } from "@/lib/status"
import { cn } from "@/lib/utils"
import { Lamp } from "@/components/Lamp"

const MAX_CHIPS = 4

function Chips({ tickets }: { tickets: Ticket[] }) {
  const navigate = useNavigate()
  const open = (id: string) => navigate(`/tickets/${id}`)
  return (
    <ul className="mt-3 space-y-1">
      {tickets.slice(0, MAX_CHIPS).map((t) => (
        <li key={t.id}>
          <button
            onClick={() => open(t.id)}
            title={t.title}
            className="block w-full truncate rounded-full border border-white/15 bg-card/40 px-3 py-1 text-left text-[13px] leading-snug shadow-sm backdrop-blur-md transition-colors hover:border-ring hover:bg-card/60"
          >
            {t.title}
          </button>
        </li>
      ))}
      {tickets.length > MAX_CHIPS && <li className="px-2 text-xs text-muted-foreground">+{tickets.length - MAX_CHIPS} more</li>}
    </ul>
  )
}

/** The pipeline as a track: one station per state, tickets stand on the station they are in. */
export function PipelineRail({ tickets }: { tickets: Ticket[] }) {
  const by = (s: TicketState) => tickets.filter((t) => t.status === s)

  return (
    <section aria-label="Ticket pipeline" className="flex min-h-[40vh] flex-col justify-center">
      <div className="relative grid grid-cols-2 gap-x-4 gap-y-8 lg:grid-cols-5">
        <div aria-hidden className="absolute left-[10%] right-[10%] top-[9px] hidden h-px bg-rail lg:block" />
        {TRACK.map((state) => {
          const list = by(state)
          const meta = STATES[state]
          const attention = meta.owner === "you" && list.length > 0
          return (
            <div key={state} className="relative min-w-0">
              <div className="flex items-center gap-2 lg:justify-center">
                <span className={cn("relative z-10 grid size-5 place-items-center rounded-full bg-background ring-1 ring-rail", attention && "ring-2 ring-primary")}>
                  <Lamp kind={list.length ? meta.lamp : "idle"} live={state === "in_progress" && list.length > 0} />
                </span>
              </div>
              <div className="mt-3 flex items-baseline gap-2.5 lg:justify-center">
                <h3 className="text-base font-semibold">{meta.label}</h3>
                <span className={cn("font-display text-3xl leading-none tabular-nums", list.length ? "text-foreground" : "text-muted-foreground")}>{list.length}</span>
              </div>
              <Chips tickets={list} />
            </div>
          )
        })}
      </div>
    </section>
  )
}
