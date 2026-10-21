import { PageHeader } from "@/components/PageHeader"
import { Skeleton } from "@/components/ui/skeleton"
import { useConfig } from "@/hooks/queries"
import { money, shortModel } from "@/lib/format"

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 border-b py-2.5 sm:grid-cols-[14rem_1fr]">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  )
}

export function Settings() {
  const { data: c, isLoading } = useConfig()
  if (isLoading || !c) return <Skeleton className="h-64 w-full" />

  return (
    <>
      <PageHeader title="Impostazioni">Sola lettura: si modificano in <span className="font-mono">projects/{c.project}.yaml</span></PageHeader>

      <section className="max-w-3xl">
        <h2 className="mb-1 text-xl font-semibold">Progetto</h2>
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
          <Row label="Tetto giornaliero">{money(c.daily_cap_effective)}</Row>
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
