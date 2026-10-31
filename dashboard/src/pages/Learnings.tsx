import { useState } from "react"
import { Link } from "react-router-dom"
import { Check, Pencil, Trash2, X } from "lucide-react"
import { PageHeader } from "@/components/PageHeader"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useKnowledge } from "@/hooks/queries"
import { useAct } from "@/hooks/useAct"
import { api, post, type LearningCategory, type PlaybookEntry, type Proposal } from "@/lib/api"
import { ago, money } from "@/lib/format"
import { cn } from "@/lib/utils"

const CATEGORIES: { id: LearningCategory; label: string; hint: string }[] = [
  { id: "where", label: "Where things live", hint: "where" },
  { id: "domain", label: "Domain rules", hint: "domain" },
  { id: "gotcha", label: "Gotchas", hint: "gotcha" },
  { id: "command", label: "Commands that work", hint: "command" },
]
const fieldClass = "w-full rounded-md border bg-background px-3 py-2 text-[13.5px]"

function Paths({ paths, missing }: { paths: string[]; missing: string[] }) {
  if (!paths.length) return null
  return (
    <ul className="mt-1.5 flex flex-wrap gap-1.5">
      {paths.map((p) => {
        const gone = missing.includes(p)
        return (
          <li key={p} className={cn("rounded-sm border px-1.5 py-0.5 font-mono text-xs", gone ? "border-lamp-red/60 text-lamp-red" : "text-muted-foreground")} title={gone ? "This path does not exist in the checkout" : undefined}>
            {p}{gone && " · not found"}
          </li>
        )
      })}
    </ul>
  )
}

function ProposalCard({ p }: { p: Proposal }) {
  const { act, pending } = useAct()
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(p.text)
  const [category, setCategory] = useState<LearningCategory>(p.category)
  const [area, setArea] = useState(p.area)
  const [paths, setPaths] = useState(p.paths.join(", "))

  const accept = (edits?: object) => act(() => post(`/api/learnings/${p.id}/accept`, edits ?? {}), "Added to the playbook")
  const saveEdit = () =>
    accept({ text, category, area, paths: paths.split(",").map((x) => x.trim()).filter(Boolean) })

  return (
    <li className="rounded-sm border p-4">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <Badge variant="secondary">{p.category}</Badge>
        {p.area && <span>{p.area}</span>}
        <span>from <span className="text-foreground">{p.source_title}</span> · {ago(p.created_at)}</span>
      </div>
      {editing ? (
        <div className="mt-3 space-y-2">
          <label className="block text-sm">Entry<textarea aria-label="Entry text" className={cn(fieldClass, "mt-1")} rows={3} value={text} onChange={(e) => setText(e.target.value)} /></label>
          <div className="grid gap-2 sm:grid-cols-3">
            <label className="text-sm">Category
              <select className={cn(fieldClass, "mt-1 h-9 py-0")} value={category} onChange={(e) => setCategory(e.target.value as LearningCategory)}>
                {CATEGORIES.map((c) => <option key={c.id} value={c.id}>{c.hint}</option>)}
              </select>
            </label>
            <label className="text-sm">Area<Input className="mt-1" value={area} onChange={(e) => setArea(e.target.value)} /></label>
            <label className="text-sm">Paths (comma separated)<Input className="mt-1 font-mono" value={paths} onChange={(e) => setPaths(e.target.value)} /></label>
          </div>
        </div>
      ) : (
        <>
          <p className="mt-2 text-[15px]">{p.text}</p>
          <Paths paths={p.paths} missing={p.missing_paths} />
        </>
      )}
      <p className="mt-2 text-xs text-muted-foreground"><span className="font-medium">Evidence:</span> {p.evidence || "none given"}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {editing ? (
          <>
            <Button size="sm" disabled={pending || !text.trim()} onClick={saveEdit} leftIcon={<Check />}>Save and accept</Button>
            <Button size="sm" variant="ghost" disabled={pending} onClick={() => setEditing(false)}>Cancel</Button>
          </>
        ) : (
          <>
            <Button size="sm" disabled={pending} onClick={() => accept()} leftIcon={<Check />}>Accept</Button>
            <Button size="sm" variant="outline" disabled={pending} onClick={() => setEditing(true)} leftIcon={<Pencil />}>Edit and accept</Button>
            <Button size="sm" variant="ghost" disabled={pending} onClick={() => act(() => post(`/api/learnings/${p.id}/reject`, {}), "Proposal rejected")} leftIcon={<X />}>Reject</Button>
          </>
        )}
      </div>
    </li>
  )
}

function EntryRow({ e }: { e: PlaybookEntry }) {
  const { act, pending } = useAct()
  const [confirming, setConfirming] = useState(false)
  return (
    <li className="flex items-start gap-3 border-b py-3 last:border-b-0">
      <div className="min-w-0 flex-1">
        <p className="text-[14.5px]">{e.text}</p>
        <Paths paths={e.paths} missing={e.missing_paths} />
        <p className="mt-1.5 text-xs text-muted-foreground">
          {e.area && <>{e.area} · </>}
          {e.source_title ? <>from {e.source_title} · </> : null}
          {e.date && <>{e.date} · </>}
          {e.uses === 0 ? "never used yet" : <>used in {e.uses} {e.uses === 1 ? "run" : "runs"}, cited {e.cited}× · last {ago(e.last_used)}</>}
        </p>
      </div>
      {confirming ? (
        <div className="flex shrink-0 gap-1">
          <Button size="xs" color="red" disabled={pending} onClick={() => act(() => api(`/api/knowledge/entries/${e.id}`, { method: "DELETE" }), "Entry deleted")}>Delete</Button>
          <Button size="xs" variant="ghost" onClick={() => setConfirming(false)}>Keep</Button>
        </div>
      ) : (
        <Button size="icon-xs" variant="ghost" aria-label={`Delete entry: ${e.text}`} onClick={() => setConfirming(true)}><Trash2 /></Button>
      )}
    </li>
  )
}

export function Learnings() {
  const { data: k, isLoading } = useKnowledge()
  if (isLoading || !k) return <Skeleton className="h-64 w-full" />
  if (!k.enabled) {
    return (
      <>
        <PageHeader title="Learnings" />
        <p className="text-muted-foreground">The playbook is turned off for this project (<code className="font-mono">knowledge.enabled</code> in the project file).</p>
      </>
    )
  }
  const pct = Math.min(100, (k.chars / k.max_chars) * 100)

  return (
    <>
      <PageHeader title="Learnings">
        Short facts the agents read before they work. Nothing is added without your OK{k.auto_propose_on_close ? "; a retrospective runs by itself when a ticket is merged" : ""}
      </PageHeader>

      <section aria-labelledby="proposals">
        <h2 id="proposals" className="mb-3 text-xl font-semibold">To review <span className="text-base font-normal text-muted-foreground">({k.proposals.length})</span></h2>
        {k.proposals.length === 0 ? (
          <p className="text-muted-foreground">No proposals waiting. They appear after a ticket is merged, or when you press “Learn from this ticket” on a closed ticket.</p>
        ) : (
          <ul className="space-y-3">{k.proposals.map((p) => <ProposalCard key={p.id} p={p} />)}</ul>
        )}
      </section>

      <section className="mt-12" aria-labelledby="playbook">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
          <h2 id="playbook" className="text-xl font-semibold">Playbook <span className="text-base font-normal text-muted-foreground">({k.entries.length})</span></h2>
          <div className="w-56 text-xs text-muted-foreground">
            <div className="flex justify-between"><span>{k.file}</span><span className="tabular-nums">{k.chars} / {k.max_chars} chars</span></div>
            <div role="progressbar" aria-label="Playbook size" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted">
              <div className={cn("h-full", pct >= 90 ? "bg-lamp-red" : "bg-primary")} style={{ width: `${pct}%` }} />
            </div>
          </div>
        </div>
        {k.chars > k.max_chars && <p className="mb-3 text-sm text-lamp-red">The playbook is longer than the limit: only the entries that fit are shown to the agents (the most relevant first). Delete the ones you no longer need.</p>}
        {k.entries.length === 0 && <p className="text-muted-foreground">The playbook is empty.</p>}
        {CATEGORIES.map((c) => {
          const list = k.entries.filter((e) => e.category === c.id)
          if (!list.length) return null
          return (
            <div key={c.id} className="mb-6">
              <h3 className="mb-1 text-base font-semibold">{c.label}</h3>
              <ul>{list.map((e) => <EntryRow key={e.id} e={e} />)}</ul>
            </div>
          )
        })}
      </section>

      <section className="mt-12" aria-labelledby="metrics">
        <h2 id="metrics" className="mb-1 text-xl font-semibold">Effort by area</h2>
        <p className="mb-2 text-sm text-muted-foreground">Averages per ticket. If the playbook works, questions, retries and rejections should go down over time.</p>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Area</TableHead>
              <TableHead className="text-right">Tickets</TableHead>
              <TableHead className="text-right">Avg cost</TableHead>
              <TableHead className="text-right">Avg turns</TableHead>
              <TableHead className="text-right">Questions asked</TableHead>
              <TableHead className="text-right">Retries</TableHead>
              <TableHead className="text-right">Checkpoint rejections</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {k.metrics.map((m) => (
              <TableRow key={m.area}>
                <TableCell>{m.area}</TableCell>
                <TableCell className="text-right tabular-nums">{m.tickets}</TableCell>
                <TableCell className="text-right tabular-nums">{money(m.avg_cost)}</TableCell>
                <TableCell className="text-right tabular-nums">{m.avg_turns.toFixed(1)}</TableCell>
                <TableCell className="text-right tabular-nums">{m.questions}</TableCell>
                <TableCell className="text-right tabular-nums">{m.retries}</TableCell>
                <TableCell className="text-right tabular-nums">{m.rejections}</TableCell>
              </TableRow>
            ))}
            {k.metrics.length === 0 && <TableRow><TableCell colSpan={7} className="text-muted-foreground">No runs recorded yet. See also <Link className="underline underline-offset-4" to="/costs">Costs</Link>.</TableCell></TableRow>}
          </TableBody>
        </Table>
      </section>
    </>
  )
}
