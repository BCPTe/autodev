import { useState } from "react"
import { Link } from "react-router-dom"
import { Check, ShieldQuestion, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useAct } from "@/hooks/useAct"
import { post, type Approval } from "@/lib/api"
import { ago } from "@/lib/format"
import { KIND_LABEL } from "@/lib/status"

function Detail({ a }: { a: Approval }) {
  const d = a.detail
  if (a.kind === "permission") {
    const input = d.input ?? {}
    const text = typeof input.command === "string" ? input.command : typeof input.file_path === "string" ? input.file_path : JSON.stringify(input)
    return <pre className="max-h-32 overflow-auto whitespace-pre-wrap rounded-sm bg-muted/70 p-2 font-mono text-[12px]">{d.tool}: {text}</pre>
  }
  return (
    <div className="space-y-2 text-[13px]">
      {d.summary && <p className="whitespace-pre-wrap">{d.summary}</p>}
      {d.checks && <ul className="font-mono text-[12px]">{d.checks.map((c) => <li key={c}>{c}</li>)}</ul>}
      {d.files && <ul className="font-mono text-[12px] text-muted-foreground">{d.files.map((f) => <li key={f}>{f}</li>)}</ul>}
      {d.notes && <p className="whitespace-pre-wrap text-muted-foreground">{d.notes}</p>}
    </div>
  )
}

/** A run is waiting for you: a permission it does not have, or a checkpoint before the next step. */
export function ApprovalCard({ a, showRun = true }: { a: Approval; showRun?: boolean }) {
  const { act, pending } = useAct()
  const [note, setNote] = useState("")
  const [denying, setDenying] = useState(false)
  const decide = (decision: "allow" | "allow_run" | "deny", done: string) =>
    act(() => post(`/api/approvals/${a.id}`, { decision, note }), done)
  const checkpoint = a.kind === "checkpoint"

  return (
    <article className="space-y-2 rounded-sm border border-lamp-amber/60 bg-lamp-amber/10 p-3" aria-label="Richiesta in attesa">
      <header className="flex items-start gap-2">
        <ShieldQuestion className="mt-0.5 size-4 shrink-0 text-lamp-amber" aria-hidden />
        <div className="min-w-0">
          <p className="font-medium">{a.title}</p>
          {showRun && (
            <p className="text-xs text-muted-foreground">
              <Link className="underline underline-offset-4" to={`/runs/${a.run_id}`}>{KIND_LABEL[a.run_kind]}: {a.ticket_title}</Link> · {ago(a.created_at)}
            </p>
          )}
        </div>
      </header>
      <Detail a={a} />
      {denying && (
        <input
          autoFocus
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Cosa deve fare invece? (l'agente lo legge)"
          aria-label="Motivo del rifiuto"
          className="h-8 w-full rounded-md border bg-background px-2 text-sm"
        />
      )}
      <div className="flex flex-wrap gap-2">
        {checkpoint ? (
          <Button size="sm" disabled={pending} onClick={() => decide("allow", "Approvato")}><Check /> Approva</Button>
        ) : (
          <>
            <Button size="sm" disabled={pending} onClick={() => decide("allow", "Consentito")}><Check /> Consenti</Button>
            <Button size="sm" variant="outline" disabled={pending} onClick={() => decide("allow_run", "Consentito per questo run")}>Consenti per questo run</Button>
          </>
        )}
        {denying ? (
          <Button size="sm" variant="destructive" disabled={pending} onClick={() => decide("deny", checkpoint ? "Rifiutato" : "Negato")}><X /> {checkpoint ? "Conferma rifiuto" : "Conferma rifiuto"}</Button>
        ) : (
          <Button size="sm" variant="ghost" disabled={pending} onClick={() => setDenying(true)}><X /> {checkpoint ? "Rifiuta" : "Nega"}</Button>
        )}
      </div>
    </article>
  )
}
