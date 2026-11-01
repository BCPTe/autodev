import { useEffect, useState, type ReactNode } from "react"
import { ArrowUp, Check, Folder, FolderGit2, X } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { api, post } from "@/lib/api"

interface ClaudeStatus { ok: boolean; installed: boolean; method?: string; email?: string; detail?: string }
interface RepoInfo {
  ok: boolean; error?: string; path: string; name: string; remote: string; github_slug: string | null
  base_branch: string; branch: string; clean: boolean; dirty: number; python: string | null
  checks: { name: string; cmd: string; cwd: string }[]; areas: string[]
}
interface Listing { ok: boolean; error?: string; path: string; parent: string | null; git: boolean; folders: { name: string; path: string; git: boolean }[] }
interface GitAccess { ok: boolean; remote: string; error: string | null; ssh_url: string | null }
interface Page { id: string; title: string; url: string | null }
interface Database { database_id: string; data_source_id: string; url: string | null }

const STEPS = ["Claude", "Repository", "Notion", "GitHub", "Finish"] as const
const PRESETS = [
  { key: "careful", title: "Careful", text: "You start everything and approve before each pull request." },
  { key: "balanced", title: "Balanced", text: "It triages by itself; you approve fixes and pull requests." },
  { key: "autonomous", title: "Autonomous", text: "It fixes low-risk tickets and opens pull requests on its own." },
] as const

/** Runs a step's action and shows its error as a toast instead of an unhandled rejection. */
async function guard(fn: () => Promise<unknown>) {
  try {
    await fn()
  } catch (e) {
    toast.error((e as Error).message)
  }
}

function Result({ ok, children }: { ok: boolean; children: ReactNode }) {
  const Icon = ok ? Check : X
  return (
    <p className={`mt-3 flex items-start gap-2 text-sm ${ok ? "text-lamp-green" : "text-destructive"}`}>
      <Icon className="mt-0.5 size-4 shrink-0" />
      <span>{children}</span>
    </p>
  )
}

function StepShell({ title, intro, children }: { title: string; intro: string; children: ReactNode }) {
  return (
    <section>
      <h2 className="text-2xl font-semibold">{title}</h2>
      <p className="mb-6 mt-1 text-muted-foreground">{intro}</p>
      <div className="space-y-4">{children}</div>
    </section>
  )
}

function ClaudeStep({ onReady }: { onReady: (ok: boolean) => void }) {
  const [status, setStatus] = useState<ClaudeStatus | null>(null)
  const check = async () => {
    const s = await api<ClaudeStatus>("/api/setup/claude")
    setStatus(s)
    onReady(s.ok)
  }
  useEffect(() => { void guard(check) }, []) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <StepShell title="Claude access" intro="autodev runs its agents through your Claude account.">
      {!status ? <p className="text-muted-foreground">Checking…</p> : status.ok ? (
        <Result ok>Signed in{status.email ? ` as ${status.email}` : ""}{status.method ? ` (${status.method})` : ""}.</Result>
      ) : (
        <>
          <Result ok={false}>{status.detail}</Result>
          <Button variant="outline" onClick={() => guard(check)}>Check again</Button>
        </>
      )}
    </StepShell>
  )
}

/** Browses the folders of the machine autodev runs on (a web page cannot read real paths from the browser). */
function FolderPicker({ start, onPick, onClose }: { start: string; onPick: (path: string) => void; onClose: () => void }) {
  const [listing, setListing] = useState<Listing | null>(null)
  const open = (path?: string) =>
    guard(async () => {
      const l = await api<Listing>(`/api/setup/browse${path ? `?path=${encodeURIComponent(path)}` : ""}`)
      if (l.ok) setListing(l)
      else toast.error(l.error ?? "Cannot open that folder")
    })
  useEffect(() => { void open(start || undefined) }, []) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="border bg-card" role="dialog" aria-label="Choose a folder">
      <div className="flex items-center gap-2 border-b p-2">
        <Button size="icon" variant="ghost" aria-label="Parent folder" disabled={!listing?.parent} onClick={() => listing?.parent && open(listing.parent)}><ArrowUp /></Button>
        <p className="min-w-0 flex-1 truncate font-mono text-sm" title={listing?.path}>{listing?.path ?? "Loading…"}</p>
        {listing?.git && <span className="shrink-0 text-xs text-muted-foreground">git repository</span>}
      </div>
      <ul className="max-h-64 overflow-y-auto">
        {listing?.folders.length === 0 && <li className="p-3 text-sm text-muted-foreground">No subfolders here.</li>}
        {listing?.folders.map((f) => (
          <li key={f.path} className="flex items-center hover:bg-accent/50">
            <button type="button" className="flex min-w-0 flex-1 items-center gap-2 px-3 py-1.5 text-left text-sm" onClick={() => open(f.path)}>
              {f.git ? <FolderGit2 className="size-4 shrink-0 text-lamp-green" /> : <Folder className="size-4 shrink-0 text-muted-foreground" />}
              <span className="truncate">{f.name}</span>
            </button>
            {f.git && <Button size="xs" variant="ghost" className="mr-2" onClick={() => onPick(f.path)}>Select</Button>}
          </li>
        ))}
      </ul>
      <div className="flex justify-end gap-2 border-t p-2">
        <Button size="sm" variant="ghost" onClick={onClose}>Cancel</Button>
        <Button size="sm" disabled={!listing} onClick={() => listing && onPick(listing.path)}>Use this folder</Button>
      </div>
    </div>
  )
}

function RepoStep({ repo, setRepo, name, setName }: { repo: RepoInfo | null; setRepo: (r: RepoInfo | null) => void; name: string; setName: (n: string) => void }) {
  const [path, setPath] = useState(repo?.path ?? "")
  const [error, setError] = useState<string | null>(null)
  const [browsing, setBrowsing] = useState(false)
  const inspect = async (target = path) => {
    const r = await post<RepoInfo>("/api/setup/repo", { path: target.trim() })
    setError(r.ok ? null : (r.error ?? "Not a usable repository"))
    setRepo(r.ok ? r : null)
    if (r.ok) setName(r.name)
  }
  return (
    <StepShell title="Your project" intro="The folder where you work on the code. autodev reads the rest from it.">
      <div className="space-y-1.5">
        <Label htmlFor="path">Folder</Label>
        <div className="flex gap-2">
          <Input id="path" value={path} onChange={(e) => setPath(e.target.value)} placeholder="/home/you/your-project" className="font-mono" autoFocus />
          <Button variant="outline" onClick={() => setBrowsing(!browsing)}>Browse…</Button>
          <Button variant="outline" onClick={() => guard(() => inspect())} disabled={!path.trim()}>Check</Button>
        </div>
      </div>
      {browsing && (
        <FolderPicker
          start={path}
          onClose={() => setBrowsing(false)}
          onPick={(p) => {
            setPath(p)
            setBrowsing(false)
            void guard(() => inspect(p))
          }}
        />
      )}
      {error && <Result ok={false}>{error}</Result>}
      {repo && (
        <>
          <Result ok>Git repository with remote <span className="font-mono">{repo.remote}</span></Result>
          <Result ok>Base branch <span className="font-mono">{repo.base_branch}</span>{repo.python ? <>, Python at <span className="font-mono">{repo.python}</span></> : null}</Result>
          {!repo.clean && <Result ok={false}>{repo.dirty} uncommitted {repo.dirty === 1 ? "file" : "files"}. Agents work on a clean tree: commit or stash before the first run.</Result>}
          <div className="space-y-1.5">
            <Label htmlFor="name">Project name</Label>
            <Input id="name" value={name} onChange={(e) => setName(e.target.value.toLowerCase())} className="max-w-xs font-mono" />
          </div>
        </>
      )}
    </StepShell>
  )
}

function NotionStep({ repo, db, setDb }: { repo: RepoInfo | null; db: Database | null; setDb: (d: Database | null) => void }) {
  const [hasToken, setHasToken] = useState(false)
  const [replace, setReplace] = useState(false)
  const [token, setToken] = useState("")
  const [pages, setPages] = useState<Page[] | null>(null)
  const [parent, setParent] = useState("")
  const [title, setTitle] = useState(`${repo?.name ?? "project"} tickets`)
  const [areas, setAreas] = useState((repo?.areas ?? []).map((a) => a[0].toUpperCase() + a.slice(1)).join(", ") || "Frontend, Backend")
  useEffect(() => { void api<{ has_notion_token: boolean }>("/api/setup/state").then((s) => setHasToken(s.has_notion_token)) }, [])
  const body = () => (token.trim() && (!hasToken || replace) ? { token: token.trim() } : {})
  const connect = async () => {
    const r = await post<{ pages: Page[] }>("/api/setup/notion/pages", body())
    setPages(r.pages)
    setParent(r.pages[0]?.id ?? "")
  }
  const create = async () => {
    const list = areas.split(",").map((a) => a.trim()).filter(Boolean)
    setDb(await post<Database>("/api/setup/notion/database", { ...body(), parent_page_id: parent, title, areas: list }))
    toast.success("Ticket database created in Notion")
  }
  return (
    <StepShell title="Where tickets live" intro="autodev creates a ticket database in Notion, with the columns it needs.">
      {hasToken && !replace ? (
        <p className="text-sm text-muted-foreground">Using the Notion token saved in <span className="font-mono">.env</span>. <button className="underline" onClick={() => setReplace(true)}>Replace it</button></p>
      ) : (
        <div className="space-y-1.5">
          <Label htmlFor="token">Integration token</Label>
          <Input id="token" type="password" value={token} onChange={(e) => setToken(e.target.value)} autoComplete="off" className="font-mono" />
          <p className="text-[13px] text-muted-foreground">notion.so/profile/integrations → New integration → copy the secret.</p>
        </div>
      )}
      {!db && <Button variant="outline" onClick={() => guard(connect)} disabled={!hasToken && !token.trim()}>Find my pages</Button>}
      {pages && pages.length === 0 && (
        <Result ok={false}>No page is shared with the integration. In Notion, create an empty page, open ··· → Connections and add the integration, then search again.</Result>
      )}
      {pages && pages.length > 0 && !db && (
        <>
          <div className="space-y-1.5">
            <Label htmlFor="parent">Create the database inside</Label>
            <select id="parent" value={parent} onChange={(e) => setParent(e.target.value)} className="h-9 w-full max-w-sm rounded-md border bg-background px-3 text-sm">
              {pages.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="dbtitle">Database name</Label>
            <Input id="dbtitle" value={title} onChange={(e) => setTitle(e.target.value)} className="max-w-sm" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="areas">Areas of the project (the Area column)</Label>
            <Input id="areas" value={areas} onChange={(e) => setAreas(e.target.value)} />
            <p className="text-[13px] text-muted-foreground">Comma separated. Triage uses them to find the right files.</p>
          </div>
          <Button onClick={() => guard(create)} disabled={!parent || !title.trim()}>Create the database</Button>
        </>
      )}
      {db && <Result ok>Database ready{db.url ? <> · <a className="underline" href={db.url} target="_blank" rel="noreferrer">open in Notion</a></> : null}</Result>}
    </StepShell>
  )
}

/** Link to GitHub's token form with name, owner, expiry and permissions already filled in (the repository is chosen there). */
function tokenLink(repo: RepoInfo, project: string) {
  const [owner] = (repo.github_slug ?? "").split("/")
  const q = new URLSearchParams({
    name: `autodev-${project}`.slice(0, 40), description: `autodev: branches and pull requests for ${repo.github_slug}`,
    ...(owner ? { target_name: owner } : {}), expires_in: "90", contents: "write", pull_requests: "write", statuses: "read",
  })
  return `https://github.com/settings/personal-access-tokens/new?${q}`
}

interface GhPlan {
  git: GitAccess
  pr: { on: boolean; login: string | null; problem: string | null }
  action: "done" | "gh_use" | "ssh" | "gh_login" | "token" | "recheck"
  gh_account: string | null
  can_continue: boolean
}
interface GhLogin { code: string | null; url: string | null; done: boolean; ok: boolean; error: string | null }

/** One line per fact, then the single action that gets the connection furthest. The server picks it. */
function GithubStep({ repo, name, token, setToken, onNext }: { repo: RepoInfo; name: string; token: string; setToken: (t: string) => void; onNext: () => void }) {
  const [plan, setPlan] = useState<GhPlan | null>(null)
  const [signIn, setSignIn] = useState<GhLogin | null>(null)
  const [draft, setDraft] = useState("")
  const refresh = async (withToken = token) => {
    const p = await post<GhPlan>("/api/setup/github/plan", { path: repo.path, slug: repo.github_slug, token: withToken.trim() || undefined })
    setPlan(p)
    return p
  }
  useEffect(() => { void guard(() => refresh()) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // while the browser sign-in is open, ask the server every couple of seconds whether it was approved
  useEffect(() => {
    if (!signIn || signIn.done) return
    const timer = setInterval(() => {
      void guard(async () => {
        const state = await api<GhLogin>("/api/setup/github/login")
        setSignIn(state)
        if (state.done) {
          if (state.error) toast.error(state.error)
          await refresh()
        }
      })
    }, 2000)
    return () => clearInterval(timer)
  }, [signIn]) // eslint-disable-line react-hooks/exhaustive-deps

  const act = (fn: () => Promise<unknown>, then?: () => void) => () => guard(async () => {
    await fn()
    const p = await refresh()
    if (then && p.pr.on) then()
  })
  const connectToken = () => guard(async () => { setToken(draft); await refresh(draft) })

  return (
    <StepShell title="Connect GitHub" intro="Agents fetch and push branches with git, and can open pull requests for you.">
      {!plan ? <p className="text-muted-foreground">Checking…</p> : (
        <>
          {plan.git.ok
            ? <Result ok>git can read <span className="font-mono">{plan.git.remote}</span></Result>
            : <Result ok={false}>git cannot read <span className="font-mono">{plan.git.remote}</span>: {plan.git.error}</Result>}
          {repo.github_slug && (plan.pr.on
            ? <Result ok>Pull requests: on{plan.pr.login ? <>, as <b>{plan.pr.login}</b></> : null}</Result>
            : <p className="mt-3 flex items-start gap-2 text-sm text-muted-foreground"><span className="mt-0.5 size-4 shrink-0 text-center">–</span>Pull requests: off. Agents stop at a local branch and you merge it from the Repo page.</p>)}

          <div className="flex flex-wrap items-center gap-4 pt-2">
            {plan.can_continue && (plan.pr.on || !repo.github_slug) && <Button onClick={onNext}>Continue</Button>}
            {plan.action === "gh_use" && plan.gh_account && (
              <Button onClick={act(() => post("/api/setup/github/use-gh", { slug: repo.github_slug, login: plan.gh_account }), onNext)}>Use your GitHub account {plan.gh_account}</Button>
            )}
            {plan.action === "ssh" && plan.git.ssh_url && <Button onClick={act(() => post("/api/setup/git/ssh", { path: repo.path }))}>Use your SSH key</Button>}
            {plan.action === "recheck" && <Button variant="outline" onClick={() => guard(() => refresh())}>Check again</Button>}
            {plan.action === "gh_login" && !signIn && (
              <Button onClick={() => guard(async () => setSignIn(await post<GhLogin>("/api/setup/github/login", {})))}>Sign in with GitHub</Button>
            )}
            {plan.action === "gh_login" && signIn && !signIn.done && (
              <div className="space-y-2">
                <p className="text-sm">Open <a className="underline" href={signIn.url ?? "https://github.com/login/device"} target="_blank" rel="noreferrer">github.com/login/device</a> and enter this code:</p>
                <p className="font-mono text-3xl font-semibold tracking-widest">{signIn.code ?? "…"}</p>
                <p className="text-[13px] text-muted-foreground">Waiting for you to approve it on GitHub…</p>
              </div>
            )}
            {plan.can_continue && repo.github_slug && !plan.pr.on && (
              <button type="button" className="text-sm text-muted-foreground underline" onClick={onNext}>Skip pull requests</button>
            )}
            {plan.action === "token" && (
              <div className="space-y-2">
                <p className="text-sm">GitHub needs a token for this repository.</p>
                <a className="inline-block text-sm underline" href={tokenLink(repo, name)} target="_blank" rel="noreferrer">Create it on GitHub</a>
                <p className="text-[13px] text-muted-foreground">The form opens filled in. Pick <span className="font-mono">{repo.github_slug?.split("/")[1]}</span> under “Only select repositories”, generate, and paste the token here.</p>
                <div className="flex gap-2">
                  <Input type="password" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="github_pat_…" autoComplete="off" className="font-mono" />
                  <Button variant="outline" onClick={connectToken} disabled={!draft.trim()}>Connect</Button>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </StepShell>
  )
}

function FinishStep({ repo, preset, setPreset, budget, setBudget, picked, setPicked }: {
  repo: RepoInfo; preset: string; setPreset: (p: string) => void; budget: string; setBudget: (b: string) => void
  picked: boolean[]; setPicked: (p: boolean[]) => void
}) {
  return (
    <StepShell title="How much on its own?" intro="You can change all of this later in Settings.">
      <div role="radiogroup" className="space-y-2">
        {PRESETS.map((p) => (
          <label key={p.key} className={`flex cursor-pointer gap-3 border p-3 ${preset === p.key ? "border-primary bg-accent/40" : ""}`}>
            <input type="radio" name="preset" checked={preset === p.key} onChange={() => setPreset(p.key)} className="mt-1" />
            <span><span className="block font-medium">{p.title}</span><span className="text-sm text-muted-foreground">{p.text}</span></span>
          </label>
        ))}
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="budget">Daily budget (USD)</Label>
        <Input id="budget" type="number" min="1" value={budget} onChange={(e) => setBudget(e.target.value)} className="max-w-[8rem]" />
      </div>
      {repo.checks.length > 0 && (
        <div>
          <p className="mb-2 text-sm font-medium">A fix counts as done when these pass</p>
          {repo.checks.map((c, i) => (
            <label key={c.name} className="flex items-center gap-2 py-1 text-sm">
              <input type="checkbox" checked={picked[i]} onChange={(e) => setPicked(picked.map((v, j) => (j === i ? e.target.checked : v)))} />
              {c.name} <span className="font-mono text-muted-foreground">{c.cmd}</span>
            </label>
          ))}
        </div>
      )}
    </StepShell>
  )
}

export function Setup() {
  const [step, setStep] = useState(0)
  const [claudeOk, setClaudeOk] = useState(false)
  const [repo, setRepo] = useState<RepoInfo | null>(null)
  const [name, setName] = useState("")
  const [db, setDb] = useState<Database | null>(null)
  const [preset, setPreset] = useState("careful")
  const [budget, setBudget] = useState("20")
  const [picked, setPicked] = useState<boolean[]>([])
  const [notices, setNotices] = useState<string[] | null>(null)
  const [ghToken, setGhToken] = useState("")
  const chooseRepo = (r: RepoInfo | null) => {
    setRepo(r)
    setPicked((r?.checks ?? []).map(() => true))
  }

  const ready = [claudeOk, !!repo && name.length > 0, !!db, false, true][step]
  const finish = async () => {
    if (!repo || !db) return
    const created = await post<{ warnings: string[] }>("/api/setup/project", {
      name, path: repo.path, repo: repo.remote, base_branch: repo.base_branch, python: repo.python,
      database_id: db.database_id, data_source_id: db.data_source_id, preset, daily_budget_usd: Number(budget) || 20,
      checks: repo.checks.filter((_, i) => picked[i]), github_slug: repo.github_slug, github_token: ghToken.trim() || undefined,
      areas: Object.fromEntries(repo.areas.map((a) => [a[0].toUpperCase() + a.slice(1), [`${a}/`]])),
    })
    if (created.warnings.length) setNotices(created.warnings)
    else window.location.reload()
  }

  if (notices) {
    return (
      <main className="mx-auto grid min-h-screen max-w-md place-items-center px-4">
        <div>
          <h1 className="text-2xl font-semibold">The project is ready</h1>
          <p className="mb-4 mt-1 text-muted-foreground">One thing to know before you start:</p>
          {notices.map((n) => <Result key={n} ok={false}>{n}</Result>)}
          <p className="mt-4 text-sm text-muted-foreground">You can add a token that sees the repository later and turn pull requests on in the project file.</p>
          <Button className="mt-6" onClick={() => window.location.reload()}>Open the dashboard</Button>
        </div>
      </main>
    )
  }

  return (
    <main className="mx-auto grid min-h-screen max-w-4xl gap-10 px-4 py-12 md:grid-cols-[12rem_1fr]">
      <nav aria-label="Setup steps">
        <h1 className="mb-6 text-lg font-semibold">Set up autodev</h1>
        <ol className="space-y-2">
          {STEPS.map((s, i) => (
            <li key={s} className={`flex items-center gap-2 text-sm ${i === step ? "font-medium" : "text-muted-foreground"}`}>
              <span className={`grid size-5 place-items-center rounded-full border text-xs ${i < step ? "border-primary bg-primary text-primary-foreground" : ""}`}>{i < step ? <Check className="size-3" /> : i + 1}</span>
              {s}
            </li>
          ))}
        </ol>
      </nav>
      <div>
        {step === 0 && <ClaudeStep onReady={setClaudeOk} />}
        {step === 1 && <RepoStep repo={repo} setRepo={chooseRepo} name={name} setName={setName} />}
        {step === 2 && <NotionStep repo={repo} db={db} setDb={setDb} />}
        {step === 3 && repo && <GithubStep repo={repo} name={name} token={ghToken} setToken={setGhToken} onNext={() => setStep(4)} />}
        {step === 4 && repo && <FinishStep repo={repo} preset={preset} setPreset={setPreset} budget={budget} setBudget={setBudget} picked={picked} setPicked={setPicked} />}
        <div className="mt-8 flex gap-2">
          {step > 0 && <Button variant="outline" onClick={() => setStep(step - 1)}>Back</Button>}
          {step === 3 ? null : step < STEPS.length - 1 ? (
            <Button onClick={() => setStep(step + 1)} disabled={!ready}>Continue</Button>
          ) : (
            <Button onClick={() => guard(finish)}>Create the project</Button>
          )}
        </div>
      </div>
    </main>
  )
}
