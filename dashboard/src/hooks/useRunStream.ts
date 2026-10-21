import { useEffect, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import type { RunEvent } from "@/lib/api"

/** Follows a run through Server-Sent Events: replays what already happened, then tails new events. */
export function useRunStream(runId: number) {
  const [events, setEvents] = useState<RunEvent[]>([])
  const [ended, setEnded] = useState(false)
  const qc = useQueryClient()

  useEffect(() => {
    setEvents([])
    setEnded(false)
    const es = new EventSource(`/api/runs/${runId}/stream`)
    es.addEventListener("event", (e) => {
      const ev = JSON.parse((e as MessageEvent).data) as RunEvent
      setEvents((prev) => (prev.some((p) => p.id === ev.id) ? prev : [...prev, ev]))
    })
    es.addEventListener("end", () => {
      setEnded(true)
      es.close()
      qc.invalidateQueries({ queryKey: ["run", runId] })
      qc.invalidateQueries({ queryKey: ["runs"] })
      qc.invalidateQueries({ queryKey: ["overview"] })
    })
    es.onerror = () => {
      // EventSource reconnects by itself with Last-Event-ID; nothing to do unless it was closed for good
    }
    return () => es.close()
  }, [runId, qc])

  return { events, ended }
}
