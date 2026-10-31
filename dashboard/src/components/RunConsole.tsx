import { useState } from "react"
import { Pause, Send } from "lucide-react"
import { ApprovalCard } from "@/components/ApprovalCard"
import { Button } from "@/components/ui/button"
import { useAct } from "@/hooks/useAct"
import { post, type Interactive } from "@/lib/api"

/** Talk to a running agent: pause it, or send an instruction that interrupts what it is doing. */
export function RunConsole({ runId, interactive }: { runId: number; interactive: Interactive }) {
  const { act, pending } = useAct()
  const [text, setText] = useState("")
  const waiting = interactive.state === "waiting"

  if (!interactive.live) {
    return <p className="mt-3 text-[13px] text-muted-foreground">This run does not accept messages: it was started from the terminal or has finished.</p>
  }

  const send = async (message: string) => {
    if (await act(() => post(`/api/runs/${runId}/message`, { text: message }), waiting ? "Message sent, the agent continues" : "Message sent: the agent stops and reads it")) setText("")
  }

  return (
    <section aria-label="Talk to the agent" className="mt-4 space-y-3">
      {interactive.approvals.map((a) => <ApprovalCard key={a.id} a={a} showRun={false} />)}
      {waiting && (
        <p role="status" className="rounded-sm border-l-2 border-lamp-amber bg-muted/60 p-2 text-[13px]">
          The agent is paused and waiting for your message.
        </p>
      )}
      <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) send(text.trim()) }}>
        <label htmlFor="agent-message" className="sr-only">Message for the agent</label>
        <textarea
          id="agent-message"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          placeholder="Write to the agent: it stops what it is doing and reads your message, keeping its context"
          className="w-full resize-y rounded-md border bg-background px-3 py-2 text-[13.5px]"
        />
        <div className="flex flex-wrap gap-2">
          <Button type="submit" size="sm" loading={pending} disabled={!text.trim()} leftIcon={<Send />}>Send</Button>
          {waiting ? (
            <Button type="button" size="sm" variant="outline" disabled={pending} onClick={() => send("Please continue where you left off.")}>Resume</Button>
          ) : (
            <Button type="button" size="sm" variant="outline" disabled={pending} onClick={() => act(() => post(`/api/runs/${runId}/pause`, {}), "Agent paused")} leftIcon={<Pause />}>Pause</Button>
          )}
        </div>
      </form>
    </section>
  )
}
