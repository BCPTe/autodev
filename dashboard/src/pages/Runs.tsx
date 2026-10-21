import { Link, useNavigate } from "react-router-dom"
import { PageHeader } from "@/components/PageHeader"
import { Lamp } from "@/components/Lamp"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useRuns } from "@/hooks/queries"
import { ago, duration, money, shortModel } from "@/lib/format"
import { KIND_LABEL, RUN_LABEL, RUN_LAMP } from "@/lib/status"

export function Runs() {
  const { data, isLoading } = useRuns()
  const navigate = useNavigate()
  return (
    <>
      <PageHeader title="Esecuzioni">Triage e fix lanciati da terminale o dalla dashboard</PageHeader>
      {isLoading && <Skeleton className="h-64 w-full" />}
      {data && data.runs.length === 0 && (
        <p className="py-6 text-muted-foreground">Ancora nessuna esecuzione. Lancia <code className="font-mono">uv run autodev triage</code> e comparirà qui.</p>
      )}
      {data && data.runs.length > 0 && (
        <div className="overflow-x-auto rounded-sm border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Stato</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Ticket</TableHead>
                <TableHead>Modello</TableHead>
                <TableHead>Esito</TableHead>
                <TableHead className="text-right">Durata</TableHead>
                <TableHead className="text-right">Costo</TableHead>
                <TableHead>Avvio</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.runs.map((r) => (
                <TableRow key={r.id} tabIndex={0} role="link" className="cursor-pointer" onClick={() => navigate(`/runs/${r.id}`)} onKeyDown={(e) => e.key === "Enter" && navigate(`/runs/${r.id}`)}>
                  <TableCell>
                    <span className="inline-flex items-center gap-2 whitespace-nowrap"><Lamp kind={RUN_LAMP[r.status]} live={r.status === "running"} />{RUN_LABEL[r.status]}</span>
                  </TableCell>
                  <TableCell>{KIND_LABEL[r.kind]}</TableCell>
                  <TableCell className="max-w-[24rem] truncate font-medium"><Link to={`/runs/${r.id}`}>{r.ticket_title}</Link></TableCell>
                  <TableCell>{shortModel(r.model)}</TableCell>
                  <TableCell>{r.outcome ?? "—"}</TableCell>
                  <TableCell className="text-right tabular-nums">{duration(r.duration)}</TableCell>
                  <TableCell className="text-right tabular-nums">{money(r.cost_usd)}</TableCell>
                  <TableCell className="whitespace-nowrap text-muted-foreground">{ago(r.started_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </>
  )
}
