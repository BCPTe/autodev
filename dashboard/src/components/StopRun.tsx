import { OctagonX } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useAct } from "@/hooks/useAct"
import { post, type Run } from "@/lib/api"

export function StopRun({ run }: { run: Run }) {
  const { act, pending } = useAct()
  if (run.status !== "running") return null
  return (
    <Button size="xs" variant="outline" disabled={pending || run.cancel_requested} onClick={() => act(() => post(`/api/runs/${run.id}/cancel`, {}), "Interruzione richiesta")}>
      <OctagonX /> {run.cancel_requested ? "Interruzione in corso..." : "Interrompi"}
    </Button>
  )
}
