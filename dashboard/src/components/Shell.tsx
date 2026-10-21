import { Link, NavLink, Outlet } from "react-router-dom"
import { Activity, BookOpenCheck, CircleDollarSign, GitBranch, GitPullRequest, LayoutDashboard, LogOut, Moon, Settings, Sun, Ticket } from "lucide-react"
import { useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { ModeSwitch, MyTurn, Notice, StopAll } from "@/components/ControlBar"
import { Lamp } from "@/components/Lamp"
import { TicketSheet } from "@/components/TicketSheet"
import { useOverview, useProjects } from "@/hooks/queries"
import { useAttention } from "@/hooks/useAttention"
import { getProject, post, setProject } from "@/lib/api"
import { money } from "@/lib/format"
import { useTheme } from "@/lib/theme"
import { cn } from "@/lib/utils"

const NAV = [
  { to: "/", label: "Panoramica", icon: LayoutDashboard, end: true },
  { to: "/tickets", label: "Ticket", icon: Ticket },
  { to: "/runs", label: "Attività", icon: Activity },
  { to: "/repo", label: "Repo", icon: GitBranch },
  { to: "/prs", label: "Pull request", icon: GitPullRequest },
  { to: "/costs", label: "Costi", icon: CircleDollarSign },
  { to: "/settings", label: "Impostazioni", icon: Settings },
]

function Budget() {
  const { data } = useOverview()
  if (!data) return null
  const pct = Math.min(100, (data.spent_today / data.daily_cap) * 100)
  const hot = pct >= 80
  return (
    <div className="flex items-center gap-3" title="Spesa di oggi rispetto al tetto giornaliero">
      <span className="hidden text-xs text-muted-foreground sm:inline">Oggi</span>
      <span className="font-display text-base tabular-nums">
        {money(data.spent_today)} <span className="text-muted-foreground">/ {money(data.daily_cap)}</span>
      </span>
      <div role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label="Budget giornaliero" className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
        <div className={cn("h-full", hot ? "bg-lamp-red" : "bg-primary")} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function Agents() {
  const { data } = useOverview()
  const n = data?.running.length ?? 0
  const asks = data?.approvals.length ?? 0
  return (
    <span className="flex items-center gap-3 text-sm">
      <span className="flex items-center gap-2">
        <Lamp kind={n ? "violet" : "idle"} live={n > 0} />
        {n ? `${n} ${n === 1 ? "agente al lavoro" : "agenti al lavoro"}` : "Nessun agente al lavoro"}
      </span>
      {asks > 0 && (
        <Link to="/" className="rounded-sm bg-lamp-amber/25 px-2 py-0.5 text-[13px] font-medium">
          {asks} {asks === 1 ? "richiesta in attesa" : "richieste in attesa"}
        </Link>
      )}
    </span>
  )
}

function ProjectSwitch() {
  const { data } = useProjects()
  if (!data || data.projects.length < 2) return null
  const current = getProject()
  return (
    <label className="mx-4 mb-2 block text-xs text-muted-foreground">
      Progetto
      <select
        className="mt-1 block h-8 w-full rounded-md border bg-background px-2 text-sm text-foreground"
        value={current ?? data.default}
        onChange={(e) => { setProject(e.target.value); window.location.assign("/") }}
      >
        {data.projects.map((p) => (
          <option key={p.name} value={p.name}>
            {p.name}{p.waiting ? ` · ${p.waiting} in attesa` : p.running ? " · al lavoro" : ""}
          </option>
        ))}
      </select>
    </label>
  )
}

export function Shell() {
  useAttention()
  const { dark, setTheme } = useTheme()
  const qc = useQueryClient()
  const logout = async () => {
    await post("/api/auth/logout", {})
    qc.clear()
    window.location.assign("/")
  }

  return (
    <div className="min-h-screen md:grid md:grid-cols-[208px_1fr]">
      <aside className="border-b bg-card md:sticky md:top-0 md:h-screen md:border-b-0 md:border-r">
        <div className="flex items-center gap-2 px-4 py-4">
          <BookOpenCheck className="size-5 text-primary" aria-hidden />
          <span className="font-display text-xl font-semibold">autodev</span>
        </div>
        <ProjectSwitch />
        <nav className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col md:overflow-visible" aria-label="Sezioni">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 whitespace-nowrap rounded-sm px-3 py-2 text-[14px] text-muted-foreground hover:bg-muted hover:text-foreground",
                  isActive && "bg-accent font-medium text-accent-foreground hover:bg-accent",
                )
              }
            >
              <Icon className="size-4" aria-hidden />
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="min-w-0">
        <header className="sticky top-0 z-20 flex flex-wrap items-center gap-x-6 gap-y-2 border-b bg-background/90 px-4 py-2.5 backdrop-blur sm:px-6">
          <Agents />
          <Budget />
          <div className="ml-auto flex items-center gap-1">
            <StopAll />
            <MyTurn />
            <div className="mx-1"><ModeSwitch /></div>
            <Button variant="ghost" size="icon" aria-label={dark ? "Passa al tema chiaro" : "Passa al tema scuro"} onClick={() => setTheme(dark ? "light" : "dark")}>
              {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </Button>
            <Button variant="ghost" size="icon" aria-label="Esci" onClick={logout}>
              <LogOut className="size-4" />
            </Button>
          </div>
        </header>
        <Notice />
        <main className="px-4 py-6 sm:px-6">
          <Outlet />
        </main>
      </div>
      <TicketSheet />
    </div>
  )
}
