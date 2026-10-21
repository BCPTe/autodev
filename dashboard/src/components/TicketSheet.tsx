import { Link, useSearchParams } from "react-router-dom"
import { ExternalLink } from "lucide-react"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { Lamp } from "@/components/Lamp"
import { StateLabel } from "@/components/StateLabel"
import { CommentBox, History, TicketControls } from "@/components/TicketControls"
import { useTicket } from "@/hooks/queries"
import { ago, duration, money, shortModel } from "@/lib/format"
import { KIND_LABEL, RUN_LABEL, RUN_LAMP, STATES } from "@/lib/status"
import { cn } from "@/lib/utils"

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="truncate">{children || "—"}</dd>
    </div>
  )
}

/** Ticket detail, opened by `?ticket=<id>` so every ticket has a shareable address. */
export function TicketSheet() {
  const [params, setParams] = useSearchParams()
  const id = params.get("ticket")
  const { data, isLoading, error } = useTicket(id)
  const close = () => setParams((p) => { const n = new URLSearchParams(p); n.delete("ticket"); return n })
  const t = data?.ticket

  return (
    <Sheet open={!!id} onOpenChange={(open) => !open && close()}>
      <SheetContent className="w-full gap-0 overflow-y-auto sm:max-w-xl">
        <SheetHeader className="border-b pb-4">
          <SheetTitle className="pr-8 text-xl leading-snug">{t?.title ?? "Ticket"}</SheetTitle>
          <SheetDescription asChild>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
              {t && <StateLabel state={t.status} />}
              {t && STATES[t.status].hint && <span className="text-muted-foreground">{STATES[t.status].hint}</span>}
            </div>
          </SheetDescription>
        </SheetHeader>

        {isLoading && <div className="space-y-3 p-4"><Skeleton className="h-5 w-2/3" /><Skeleton className="h-32 w-full" /></div>}
        {error && <p className="p-4 text-destructive">Impossibile leggere il ticket: {(error as Error).message}</p>}

        {t && data && (
          <div className="space-y-6 p-4">
            <TicketControls ticket={t} />

            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
              <Field label="Area">{t.area}</Field>
              <Field label="Priorità">{t.priority}</Field>
              <Field label="Rischio">{t.risk}</Field>
              <Field label="Tentativi di fix">{t.attempts}</Field>
              <Field label="Costo">{money(t.cost_usd)}</Field>
              <Field label="Esito verifica">{t.verification}</Field>
              <Field label="Aggiornato">{ago(t.updated_at)}</Field>
            </dl>

            {(t.branch || t.pr_url) && (
              <div className="space-y-1 text-[13px]">
                {t.branch && <p className="font-mono">{t.branch}</p>}
                {t.pr_url && (
                  <a href={t.pr_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline">
                    Pull request <ExternalLink className="size-3.5" />
                  </a>
                )}
              </div>
            )}

            {t.agent_note && (
              <section>
                <h3 className="mb-1 text-base font-semibold">Nota dell'agente</h3>
                <p className="whitespace-pre-wrap rounded-sm border-l-2 border-lamp-amber bg-muted/60 p-3 text-[13px]">{t.agent_note}</p>
              </section>
            )}

            <section>
              <h3 className="mb-1 text-base font-semibold">Descrizione</h3>
              <p className="whitespace-pre-wrap text-[13.5px] leading-relaxed">{t.body || "Nessuna descrizione."}</p>
            </section>

            <section>
              <h3 className="mb-2 text-base font-semibold">Commenti</h3>
              {data.comments.length === 0 && <p className="text-muted-foreground">Nessun commento.</p>}
              <ol className="space-y-3">
                {data.comments.map((c, i) => (
                  <li key={i} className={cn("rounded-sm border p-3", c.is_bot ? "bg-card" : "border-primary/30 bg-accent/40")}>
                    <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
                      <Lamp kind={c.is_bot ? "violet" : "blue"} className="size-2" />
                      <span className="font-medium text-foreground">{c.author}</span>
                      <span>{ago(c.created_at)}</span>
                    </div>
                    <p className="whitespace-pre-wrap text-[13px] leading-relaxed">{c.text}</p>
                  </li>
                ))}
              </ol>
              <CommentBox ticketId={t.id} />
            </section>

            <section>
              <h3 className="mb-2 text-base font-semibold">Attività</h3>
              {data.runs.length === 0 && <p className="text-muted-foreground">Nessuna attività registrata.</p>}
              <ul className="divide-y rounded-sm border">
                {data.runs.map((r) => (
                  <li key={r.id}>
                    <Link to={`/runs/${r.id}`} className="flex items-center gap-3 px-3 py-2 hover:bg-muted/60">
                      <Lamp kind={RUN_LAMP[r.status]} live={r.status === "running"} />
                      <span className="font-medium">{KIND_LABEL[r.kind]}</span>
                      <span className="text-muted-foreground">{RUN_LABEL[r.status]} · {shortModel(r.model)}</span>
                      <span className="ml-auto tabular-nums text-muted-foreground">{duration(r.duration)} · {money(r.cost_usd)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>

            <History actions={data.actions} />

            {t.url && (
              <a href={t.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm text-primary underline-offset-4 hover:underline">
                Apri in Notion <ExternalLink className="size-3.5" />
              </a>
            )}
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}
