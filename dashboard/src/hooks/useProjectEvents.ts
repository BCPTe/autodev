import { useEffect } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useVisible } from "@/hooks/useVisible"
import { scoped } from "@/lib/api"

/** Which cached queries each server topic invalidates. */
const TOPICS: Record<string, string[][]> = {
  runs: [["runs"], ["run"], ["overview"], ["ticket"], ["tickets"], ["costs"], ["repo"], ["prs"], ["diff"]],
  approvals: [["overview"], ["run"]],
  actions: [["ticket"], ["tickets"], ["overview"]],
  control: [["overview"]],
  knowledge: [["knowledge"]],
  tickets: [["ticket"], ["tickets"], ["overview"]],
}

/** Follows the project's change stream and refetches only what changed, instead of polling everything. */
export function useProjectEvents() {
  const qc = useQueryClient()
  const visible = useVisible()
  useEffect(() => {
    if (!visible) return
    const es = new EventSource(scoped("/api/events"))
    es.addEventListener("change", (e) => {
      const keys = new Map<string, string[]>()
      for (const topic of JSON.parse((e as MessageEvent).data) as string[]) for (const k of TOPICS[topic] ?? []) keys.set(k[0], k)
      keys.forEach((queryKey) => qc.invalidateQueries({ queryKey }))
    })
    // on (re)connecting (back to this tab, server restart, sleep) anything may have changed in between
    es.addEventListener("open", () => qc.invalidateQueries())
    return () => es.close()
  }, [qc, visible])
}
