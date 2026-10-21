import { useState } from "react"
import { Link } from "react-router-dom"
import { FlaskConical, Trash2, Undo2 } from "lucide-react"
import { DiffView } from "@/components/DiffView"
import { PageHeader } from "@/components/PageHeader"
import { Lamp } from "@/components/Lamp"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useConfig, useRepo } from "@/hooks/queries"
import { useAct } from "@/hooks/useAct"
import { post } from "@/lib/api"
import { ago } from "@/lib/format"

export function Repo() {
  const { data: r, isLoading } = useRepo()
  const { data: config } = useConfig()
  const { act, pending } = useAct()
  const [diff, setDiff] = useState<string | "working" | null>(null)
  if (isLoading || !r) return <Skeleton className="h-64 w-full" />
  const locked = r.busy ? "Un agente sta lavorando sul checkout" : null
  const removable = r.branches.filter((b) => b.merged && !b.current)
  const switchTo = (branch: string, done: string) => act(() => post("/api/repo/checkout", { branch }), done)

  return (
    <>
      <PageHeader title="Repo">{r.path}</PageHeader>

      <div className="mb-6 flex flex-wrap items-center gap-2">
        {r.on_agent_branch && (
          <Button size="sm" variant="outline" disabled={pending || !!locked || !r.clean} title={locked ?? (r.clean ? undefined : "Prima fai commit o stash delle modifiche")} onClick={() => switchTo(r.base_branch, `Sei tornato su ${r.base_branch}`)}>
            <Undo2 /> Torna a {r.base_branch}
          </Button>
        )}
        {config?.has_checks && (
          <Button size="sm" variant="outline" disabled={pending || !!locked} title={locked ?? "Esegue i controlli del progetto (test, typecheck) sul codice com'è ora"} onClick={() => act(() => post("/api/repo/checks", {}), "Controlli avviati: guarda Attività")}>
            <FlaskConical /> Esegui i controlli
          </Button>
        )}
        {removable.length > 0 && (
          <Button size="sm" variant="outline" disabled={pending || !!locked} onClick={() => act(() => post("/api/repo/cleanup", {}), `${removable.length} branch eliminati`)}>
            <Trash2 /> Elimina i {removable.length} branch già uniti
          </Button>
        )}
        {locked && <span className="text-[13px] text-muted-foreground">{locked}</span>}
      </div>

      <section className="grid gap-x-10 gap-y-6 sm:grid-cols-2 lg:grid-cols-4" aria-label="Stato del checkout">
        <div>
          <p className="text-xs text-muted-foreground">Branch attivo</p>
          <p className="flex items-center gap-2 font-mono text-[15px]"><Lamp kind={r.on_agent_branch ? "amber" : "green"} />{r.branch}</p>
          <p className="mt-1 text-[13px] text-muted-foreground">{r.on_agent_branch ? "Sei sul branch di un agente: Docker serve il suo codice." : `Sei sul branch di base (${r.base_branch}).`}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Modifiche non committate</p>
          <p className="flex items-center gap-2 text-[15px]"><Lamp kind={r.clean ? "green" : "red"} />{r.clean ? "Nessuna" : `${r.dirty.length} file`}</p>
          <p className="mt-1 text-[13px] text-muted-foreground">{r.clean ? "Un agente può partire." : "Un agente non parte finché non fai commit o stash."}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Rispetto a origin/{r.base_branch}</p>
          <p className="font-display text-xl tabular-nums">{r.ahead ?? "?"} avanti · {r.behind ?? "?"} indietro</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Agente al lavoro</p>
          <p className="flex items-center gap-2 text-[15px]"><Lamp kind={r.busy ? "violet" : "idle"} live={r.busy} />{r.busy ? "Un fix è in corso" : "Libero"}</p>
        </div>
      </section>

      {!r.clean && (
        <section className="mt-8">
          <h2 className="mb-2 text-xl font-semibold">File modificati</h2>
          <ul className="rounded-sm border bg-card p-3 font-mono text-[12.5px]">
            {r.dirty.map((line) => <li key={line}>{line}</li>)}
          </ul>
          <button className="mt-2 text-[13px] text-primary underline-offset-4 hover:underline" onClick={() => setDiff(diff === "working" ? null : "working")}>
            {diff === "working" ? "Nascondi le differenze" : "Vedi le differenze"}
          </button>
          {diff === "working" && <div className="mt-2"><DiffView branch={null} /></div>}
        </section>
      )}

      <section className="mt-10">
        <h2 className="mb-2 text-xl font-semibold">Branch degli agenti</h2>
        {r.branches.length === 0 ? (
          <p className="text-muted-foreground">Nessun branch <span className="font-mono">autodev/*</span>. Compaiono dopo il primo fix.</p>
        ) : (
          <div className="overflow-x-auto rounded-sm border bg-card">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Branch</TableHead>
                  <TableHead>Stato</TableHead>
                  <TableHead className="text-right">Commit in più</TableHead>
                  <TableHead>Ultimo commit</TableHead>
                  <TableHead>Aggiornato</TableHead>
                  <TableHead><span className="sr-only">Azioni</span></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {r.branches.map((b) => (
                  <TableRow key={b.name}>
                    <TableCell className="font-mono text-[12.5px]">{b.name}</TableCell>
                    <TableCell>
                      <span className="inline-flex items-center gap-2 whitespace-nowrap">
                        <Lamp kind={b.current ? "amber" : b.merged ? "idle" : "blue"} />
                        {b.current ? "Attivo" : b.merged ? "Già unito: si può eliminare" : "Da unire"}
                      </span>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{b.ahead}</TableCell>
                    <TableCell className="max-w-[22rem] truncate">{b.last_commit}</TableCell>
                    <TableCell className="whitespace-nowrap text-muted-foreground">{ago(b.updated)}</TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        <Button size="xs" variant="ghost" onClick={() => setDiff(diff === b.name ? null : b.name)}>{diff === b.name ? "Nascondi" : "Diff"}</Button>
                        {!b.current && (
                          <Button size="xs" variant="ghost" disabled={pending || !!locked || !r.clean} title="Passa a questo branch per provarlo in locale" onClick={() => switchTo(b.name, `Sei su ${b.name}`)}>Prova</Button>
                        )}
                        {b.merged && !b.current && (
                          <Button size="xs" variant="ghost" disabled={pending || !!locked} onClick={() => act(() => post("/api/repo/cleanup", { names: [b.name] }), "Branch eliminato")}>Elimina</Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        {diff && diff !== "working" && <div className="mt-4"><h3 className="mb-2 font-display text-base font-semibold">Modifiche di <span className="font-mono text-sm">{diff}</span> rispetto a {r.base_branch}</h3><DiffView branch={diff} /></div>}
        <p className="mt-2 text-[13px] text-muted-foreground">Le pull request di questi branch sono in <Link className="underline underline-offset-4" to="/prs">Pull request</Link>.</p>
      </section>

      <section className="mt-10">
        <h2 className="mb-2 text-xl font-semibold">Ultimi commit</h2>
        <ul className="divide-y border-y">
          {r.commits.map((c) => (
            <li key={c.sha} className="flex gap-4 py-1.5">
              <span className="w-16 shrink-0 font-mono text-[12.5px] text-muted-foreground">{c.sha}</span>
              <span className="truncate">{c.subject}</span>
            </li>
          ))}
        </ul>
      </section>
    </>
  )
}
