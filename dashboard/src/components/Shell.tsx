import { useEffect, useState } from "react"
import { Link, NavLink, Outlet, useLocation } from "react-router-dom"
import { Activity, BookOpenCheck, CircleDollarSign, GitBranch, GitPullRequest, LayoutDashboard, ChevronDown, Lightbulb, LogOut, Moon, Settings, Sun, Ticket } from "lucide-react"
import { useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
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
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/tickets", label: "Tickets", icon: Ticket },
  { to: "/runs", label: "Activity", icon: Activity },
  { to: "/repo", label: "Repo", icon: GitBranch },
  { to: "/prs", label: "Pull requests", icon: GitPullRequest },
  { to: "/learnings", label: "Learnings", icon: Lightbulb },
  { to: "/costs", label: "Costs", icon: CircleDollarSign },
  { to: "/settings", label: "Settings", icon: Settings },
]

function Budget() {
  const { data } = useOverview()
  if (!data) return null
  const pct = Math.min(100, (data.spent_today / data.daily_cap) * 100)
  const hot = pct >= 80
  return (
    <div className="flex items-center gap-3" title="Today's spend against the daily cap">
      <span className="hidden text-xs text-muted-foreground sm:inline">Today</span>
      <span className="font-display text-base tabular-nums">
        {money(data.spent_today)} <span className="text-muted-foreground">/ {money(data.daily_cap)}</span>
      </span>
      <div role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label="Daily budget" className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
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
      {n ? (
        <DropdownMenu>
          <DropdownMenuTrigger className="flex items-center gap-2 rounded-md px-2 py-1 hover:bg-muted">
            <Lamp kind="violet" live />
            {n} {n === 1 ? "agent working" : "agents working"}
            <ChevronDown className="size-3.5 text-muted-foreground" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-72">
            {data?.running.map((r) => (
              <DropdownMenuItem key={r.id} asChild>
                <Link to={`/runs/${r.id}`} className="flex flex-col items-start gap-0.5">
                  <span className="w-full truncate font-medium">{r.ticket_title}</span>
                  <span className="text-xs text-muted-foreground">{r.ticket_id} · {r.kind}</span>
                </Link>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : (
        <span className="flex items-center gap-2">
          <Lamp kind="idle" />
          No agent working
        </span>
      )}
      {asks > 0 && (
        <Link to="/" className="rounded-sm bg-lamp-amber/25 px-2 py-0.5 text-[13px] font-medium">
          {asks} {asks === 1 ? "request waiting" : "requests waiting"}
        </Link>
      )}
    </span>
  )
}

function NextCheck() {
  const { data } = useOverview()
  const [now, setNow] = useState(() => Date.now() / 1000)
  const next = data?.control.next_check ?? null
  useEffect(() => {
    if (next === null) return
    const t = setInterval(() => setNow(Date.now() / 1000), 1000)
    return () => clearInterval(t)
  }, [next])
  if (next === null) return null
  const left = Math.max(0, Math.ceil(next - now))
  return (
    <span className="text-sm text-muted-foreground" title="Time until the next check of the open tickets">
      Next check {left > 0 ? <span className="tabular-nums text-foreground">{Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")}</span> : "in progress…"}
    </span>
  )
}

function ProjectSwitch() {
  const { data } = useProjects()
  if (!data || data.projects.length < 2) return null
  const current = getProject()
  return (
    <label className="mx-4 mb-2 block text-xs text-muted-foreground">
      Project
      <select
        className="mt-1 block h-8 w-full rounded-md border bg-background px-2 text-sm text-foreground"
        value={current ?? data.default}
        onChange={(e) => { setProject(e.target.value); window.location.assign("/") }}
      >
        {data.projects.map((p) => (
          <option key={p.name} value={p.name}>
            {p.name}{p.waiting ? ` · ${p.waiting} waiting` : p.running ? " · working" : ""}
          </option>
        ))}
      </select>
    </label>
  )
}

export function Shell() {
  useAttention()
  const { pathname } = useLocation()
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
        <nav className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col md:overflow-visible" aria-label="Sections">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 whitespace-nowrap rounded-sm px-3 py-2 text-[14px] text-muted-foreground hover:bg-muted hover:text-foreground",
                  isActive && "bg-accent font-medium text-accent-foreground shadow-[inset_2px_0_0_var(--primary)] hover:bg-accent",
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
          <NextCheck />
          <Budget />
          <div className="ml-auto flex items-center gap-1">
            <StopAll />
            <MyTurn />
            <div className="mx-1"><ModeSwitch /></div>
            <Button variant="ghost" size="icon" aria-label={dark ? "Switch to light theme" : "Switch to dark theme"} onClick={() => setTheme(dark ? "light" : "dark")}>
              {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </Button>
            <Button variant="ghost" size="icon" aria-label="Sign out" onClick={logout}>
              <LogOut className="size-4" />
            </Button>
          </div>
        </header>
        <Notice />
        <main className="mx-auto max-w-[1280px] px-4 py-8 sm:px-8">
          <div key={pathname} className="page-in"><Outlet /></div>
        </main>
      </div>
      <TicketSheet />
    </div>
  )
}
