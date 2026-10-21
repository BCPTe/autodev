import type { TicketState } from "@/lib/api"
import { STATES } from "@/lib/status"
import { Lamp } from "@/components/Lamp"

export function StateLabel({ state }: { state: TicketState }) {
  const meta = STATES[state]
  return (
    <span className="inline-flex items-center gap-2 whitespace-nowrap">
      <Lamp kind={meta.lamp} />
      {meta.label}
    </span>
  )
}
