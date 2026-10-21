import { PageHeader } from "@/components/PageHeader"
import { Lamp } from "@/components/Lamp"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useRepo } from "@/hooks/queries"
import { ago } from "@/lib/format"

export function Repo() {
  const { data: r, isLoading } = useRepo()
  if (isLoading || !r) return <Skeleton className="h-64 w-full" />

  return (
    <>
      <PageHeader title="Repo">{r.path}</PageHeader>

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
          <p className="text-xs text-muted-foreground">Agente sul checkout</p>
          <p className="flex items-center gap-2 text-[15px]"><Lamp kind={r.busy ? "violet" : "idle"} live={r.busy} />{r.busy ? "Un fix è in corso" : "Libero"}</p>
        </div>
      </section>

      {!r.clean && (
        <section className="mt-8">
          <h2 className="mb-2 text-xl font-semibold">File modificati</h2>
          <ul className="rounded-sm border bg-card p-3 font-mono text-[12.5px]">
            {r.dirty.map((line) => <li key={line}>{line}</li>)}
          </ul>
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
                  <TableHead className="text-right">Commit avanti</TableHead>
                  <TableHead>Ultimo commit</TableHead>
                  <TableHead>Aggiornato</TableHead>
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
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
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
