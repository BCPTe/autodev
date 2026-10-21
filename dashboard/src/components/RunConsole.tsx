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
    return <p className="mt-3 text-[13px] text-muted-foreground">Questo run non accetta messaggi: è partito da terminale oppure è terminato.</p>
  }

  const send = async (message: string) => {
    if (await act(() => post(`/api/runs/${runId}/message`, { text: message }), waiting ? "Messaggio inviato, l'agente riparte" : "Messaggio inviato: l'agente si ferma e lo legge")) setText("")
  }

  return (
    <section aria-label="Parla con l'agente" className="mt-4 space-y-3">
      {interactive.approvals.map((a) => <ApprovalCard key={a.id} a={a} showRun={false} />)}
      {waiting && (
        <p role="status" className="rounded-sm border-l-2 border-lamp-amber bg-muted/60 p-2 text-[13px]">
          L'agente è in pausa e aspetta un tuo messaggio.
        </p>
      )}
      <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) send(text.trim()) }}>
        <label htmlFor="agent-message" className="sr-only">Messaggio per l'agente</label>
        <textarea
          id="agent-message"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          placeholder="Scrivi all'agente: ferma ciò che sta facendo e legge il messaggio, senza perdere il contesto"
          className="w-full resize-y rounded-md border bg-background px-3 py-2 text-[13.5px]"
        />
        <div className="flex flex-wrap gap-2">
          <Button type="submit" size="sm" disabled={pending || !text.trim()}><Send /> Invia</Button>
          {waiting ? (
            <Button type="button" size="sm" variant="outline" disabled={pending} onClick={() => send("Continua pure da dove eri rimasto.")}>Riprendi</Button>
          ) : (
            <Button type="button" size="sm" variant="outline" disabled={pending} onClick={() => act(() => post(`/api/runs/${runId}/pause`, {}), "Agente in pausa")}><Pause /> Pausa</Button>
          )}
        </div>
      </form>
    </section>
  )
}
