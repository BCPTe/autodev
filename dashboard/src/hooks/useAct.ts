import { useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

/** Runs a mutation, reports the outcome as a toast and refreshes everything the dashboard shows. */
export function useAct() {
  const qc = useQueryClient()
  const [pending, setPending] = useState(false)
  const act = async (fn: () => Promise<unknown>, done?: string | ((result: unknown) => string)) => {
    setPending(true)
    try {
      const result = await fn()
      if (done) toast.success(typeof done === "function" ? done(result) : done)
      await qc.invalidateQueries()
      return true
    } catch (e) {
      toast.error((e as Error).message)
      return false
    } finally {
      setPending(false)
    }
  }
  return { act, pending }
}
