import { useState } from "react"
import { Link } from "react-router-dom"
import { FlaskConical, Trash2, Undo2 } from "lucide-react"
import { DiffView } from "@/components/DiffView"
import { PushPanel } from "@/components/PushPanel"
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
  const locked = r.busy ? "An agent is working on the checkout" : null
  const removable = r.branches.filter((b) => b.merged && !b.current)
  const switchTo = (branch: string, done: string) => act(() => post("/api/repo/checkout", { branch }), done)

  return (
    <>
      <PageHeader title="Repo">{r.path}</PageHeader>

      <div className="mb-8 flex flex-wrap items-center gap-2">
        {r.on_agent_branch && (
          <Button size="sm" variant="outline" disabled={pending || !!locked || !r.clean} title={locked ?? (r.clean ? undefined : "Commit or stash your changes first")} onClick={() => switchTo(r.base_branch, `Back on ${r.base_branch}`)} leftIcon={<Undo2 />}>Back to {r.base_branch}</Button>
        )}
        {config?.has_checks && (
          <Button size="sm" variant="outline" disabled={pending || !!locked} title={locked ?? "Runs the project's checks (tests, typecheck) on the code as it is now"} onClick={() => act(() => post("/api/repo/checks", {}), "Checks started. Follow them in Activity")} leftIcon={<FlaskConical />}>Run checks</Button>
        )}
        {removable.length > 0 && (
          <Button size="sm" variant="outline" disabled={pending || !!locked} onClick={() => act(() => post("/api/repo/cleanup", {}), `${removable.length} ${removable.length === 1 ? "branch" : "branches"} deleted`)} leftIcon={<Trash2 />}>Delete {removable.length} merged {removable.length === 1 ? "branch" : "branches"}</Button>
        )}
        {r.clones > 0 && (
          <Button size="sm" variant="outline" disabled={pending || !!locked} title="Throwaway copies of the project that agents left in workspaces/" onClick={() => act(() => post("/api/repo/cleanup", { names: [], clones: true }), `${r.clones} ${r.clones === 1 ? "clone" : "clones"} removed`)} leftIcon={<Trash2 />}>Remove {r.clones} leftover {r.clones === 1 ? "clone" : "clones"}</Button>
        )}
        {locked && <span className="text-[13px] text-muted-foreground">{locked}</span>}
      </div>

      <div className="mb-8"><PushPanel quiet /></div>

      <section className="grid divide-y border-y bg-card sm:grid-cols-2 sm:divide-y-0 lg:grid-cols-4 lg:divide-x [&>div]:p-4" aria-label="Checkout state">
        <div>
          <p className="mb-1 text-xs uppercase tracking-[0.06em] text-muted-foreground">Current branch</p>
          <p className="flex items-center gap-2 font-mono text-[15px]"><Lamp kind={r.on_agent_branch ? "amber" : "green"} />{r.branch}</p>
          <p className="mt-1 text-[13px] text-muted-foreground">{r.on_agent_branch ? "This is an agent's branch, so Docker is serving its code." : `This is the base branch (${r.base_branch}).`}</p>
        </div>
        <div>
          <p className="mb-1 text-xs uppercase tracking-[0.06em] text-muted-foreground">Uncommitted changes</p>
          <p className="flex items-center gap-2 text-[15px]"><Lamp kind={r.clean ? "green" : "red"} />{r.clean ? "None" : `${r.dirty.length} ${r.dirty.length === 1 ? "file" : "files"}`}</p>
          <p className="mt-1 text-[13px] text-muted-foreground">{r.clean ? "An agent can start." : "No agent can start until you commit or stash them."}</p>
        </div>
        <div>
          <p className="mb-1 text-xs uppercase tracking-[0.06em] text-muted-foreground">Compared with origin/{r.base_branch}</p>
          <p className="font-display text-xl tabular-nums">{r.ahead ?? "?"} ahead · {r.behind ?? "?"} behind</p>
        </div>
        <div>
          <p className="mb-1 text-xs uppercase tracking-[0.06em] text-muted-foreground">Agent status</p>
          <p className="flex items-center gap-2 text-[15px]"><Lamp kind={r.busy ? "violet" : "idle"} live={r.busy} />{r.busy ? "A fix is running" : "Idle"}</p>
        </div>
      </section>

      {!r.clean && (
        <section className="mt-12">
          <h2 className="section-title">Changed files</h2>
          <ul className="rounded-sm border bg-card p-3 font-mono text-[12.5px]">
            {r.dirty.map((line) => <li key={line}>{line}</li>)}
          </ul>
          <button className="mt-2 text-[13px] text-primary underline-offset-4 hover:underline" onClick={() => setDiff(diff === "working" ? null : "working")}>
            {diff === "working" ? "Hide the changes" : "View the changes"}
          </button>
          {diff === "working" && <div className="mt-2"><DiffView branch={null} /></div>}
        </section>
      )}

      <section className="mt-14">
        <h2 className="section-title">Agent branches</h2>
        {r.branches.length === 0 ? (
          <p className="text-muted-foreground">No <span className="font-mono">autodev/*</span> branches yet. The first fix creates one.</p>
        ) : (
          <div className="overflow-x-auto rounded-sm border bg-card">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Branch</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Commits ahead</TableHead>
                  <TableHead>Last commit</TableHead>
                  <TableHead>Updated</TableHead>
                  <TableHead><span className="sr-only">Actions</span></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {r.branches.map((b) => (
                  <TableRow key={b.name}>
                    <TableCell className="font-mono text-[12.5px]">{b.name}</TableCell>
                    <TableCell>
                      <span className="inline-flex items-center gap-2 whitespace-nowrap">
                        <Lamp kind={b.current ? "amber" : b.merged ? "idle" : "blue"} />
                        {b.current ? "Active" : b.merged ? "Merged, safe to delete" : "Not merged"}
                      </span>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{b.ahead}</TableCell>
                    <TableCell className="max-w-[22rem] truncate">{b.last_commit}</TableCell>
                    <TableCell className="whitespace-nowrap text-muted-foreground">{ago(b.updated)}</TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        <Button size="xs" variant="ghost" onClick={() => setDiff(diff === b.name ? null : b.name)}>{diff === b.name ? "Hide" : "Diff"}</Button>
                        {!b.current && (
                          <Button size="xs" variant="ghost" disabled={pending || !!locked || !r.clean} title="Check out this branch to try it locally" onClick={() => switchTo(b.name, `Now on ${b.name}`)}>Try</Button>
                        )}
                        {b.merged && !b.current && (
                          <Button size="xs" variant="ghost" disabled={pending || !!locked} onClick={() => act(() => post("/api/repo/cleanup", { names: [b.name] }), "Branch deleted")}>Delete</Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        {diff && diff !== "working" && <div className="mt-4"><h3 className="mb-2 font-display text-base font-semibold">Changes in <span className="font-mono text-sm">{diff}</span> against {r.base_branch}</h3><DiffView branch={diff} /></div>}
        <p className="mt-2 text-[13px] text-muted-foreground">Pull requests for these branches are under <Link className="underline underline-offset-4" to="/prs">Pull requests</Link>.</p>
      </section>

      <section className="mt-14">
        <h2 className="section-title">Latest commits</h2>
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
