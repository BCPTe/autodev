import { PageHeader } from "@/components/PageHeader"
import { Skeleton } from "@/components/ui/skeleton"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useConfig, useOverview } from "@/hooks/queries"
import { useAct } from "@/hooks/useAct"
import { put } from "@/lib/api"
import { MODES } from "@/components/ControlBar"
import { money, shortModel } from "@/lib/format"

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 border-b py-2.5 sm:grid-cols-[14rem_1fr]">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  )
}

function DailyCap({ current }: { current: number }) {
  const { act, pending } = useAct()
  const [value, setValue] = useState(String(current))
  const n = Number(value)
  const valid = Number.isFinite(n) && n > 0 && n <= 1000
  return (
    <form className="flex items-center gap-2" onSubmit={(e) => { e.preventDefault(); if (valid) act(() => put("/api/control", { daily_budget_usd: n }), "Tetto giornaliero aggiornato") }}>
      <span aria-hidden>$</span>
      <Input aria-label="Tetto giornaliero in dollari" className="h-8 w-24" inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} />
      <Button type="submit" size="sm" variant="outline" disabled={pending || !valid || n === current}>Salva</Button>
    </form>
  )
}

export function Settings() {
  const { data: c, isLoading } = useConfig()
  const { data: overview } = useOverview()
  if (isLoading || !c) return <Skeleton className="h-64 w-full" />
  const control = overview?.control

  return (
    <>
      <PageHeader title="Impostazioni">Autonomia e tetto giornaliero si cambiano qui; il resto in <span className="font-mono">projects/{c.project}.yaml</span></PageHeader>

      <section className="max-w-3xl">
        <h2 className="mb-1 text-xl font-semibold">Autonomia</h2>
        <dl>
          <Row label="Modalità">{MODES.find((m) => m.id === control?.mode)?.label}: <span className="text-muted-foreground">{MODES.find((m) => m.id === control?.mode)?.hint}</span></Row>
          <Row label="Approvazione automatica">Solo rischio {c.autonomy.auto_approve_risks.join(" e ")} (in modalità Auto)</Row>
          <Row label="Controllo del tabellone">Ogni {c.autonomy.poll_seconds} secondi (in Auto e Supervisionato)</Row>
          <Row label="Nuovo tentativo dopo un errore">Dopo {Math.round(c.autonomy.retry_cooldown_seconds / 60)} minuti, oppure a mano</Row>
          <Row label="Punti di approvazione">{c.autonomy.checkpoints.length ? c.autonomy.checkpoints.map((k) => (k === "after_agent" ? "dopo l'agente, prima delle verifiche" : "prima della pull request")).join("; ") + " (non in modalità Auto)" : "Nessuno"}</Row>
          <Row label="Tetto giornaliero"><DailyCap key={c.daily_cap_effective} current={c.daily_cap_effective} /></Row>
        </dl>

        <h2 className="mb-1 mt-10 text-xl font-semibold">Progetto</h2>
        <dl>
          <Row label="Repository">{c.repo}</Row>
          <Row label="Branch di base">{c.base_branch}</Row>
          <Row label="Cartella locale"><span className="font-mono text-[13px]">{c.local_path}</span></Row>
          <Row label="Dove lavora l'agente">{c.workspace_mode === "inplace" ? "Nel checkout del progetto, su un branch dedicato" : "In un clone separato"}</Row>
          <Row label="Pull request automatiche">{c.pr_enabled ? "Attive" : "Disattivate"}</Row>
        </dl>

        <h2 className="mb-1 mt-10 text-xl font-semibold">Limiti</h2>
        <dl>
          <Row label="Tetto per ticket">{money(c.limits.budget_usd_per_ticket)}</Row>
          <Row label="Tentativi dentro un run">{c.limits.max_attempts}</Row>
          <Row label="Lanci di fix per ticket">{c.limits.max_fix_runs}</Row>
          <Row label="File modificabili per fix">{c.limits.max_files}</Row>
        </dl>

        <h2 className="mb-1 mt-10 text-xl font-semibold">Agenti</h2>
        <dl>
          {Object.entries(c.agents).map(([name, a]) => (
            <Row key={name} label={name === "triage" ? "Triage" : "Fix"}>{a.models.map(shortModel).join(" → ")} · fino a {a.max_turns} turni</Row>
          ))}
          <Row label="Modelli selezionabili nel ticket">{Object.entries(c.model_choices).map(([k, v]) => `${k} (${v})`).join(", ")}</Row>
        </dl>

        <h2 className="mb-1 mt-10 text-xl font-semibold">Percorsi ad alto rischio</h2>
        <p className="mb-2 text-muted-foreground">Le modifiche a questi file alzano il rischio a Alto.</p>
        <ul className="font-mono text-[13px]">{c.never_automerge.map((p) => <li key={p}>{p}</li>)}</ul>
      </section>
    </>
  )
}
