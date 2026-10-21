import { NavLink, Outlet } from "react-router-dom"
import { Activity, BookOpenCheck, CircleDollarSign, GitBranch, LayoutDashboard, LogOut, Moon, Settings, Sun, Ticket } from "lucide-react"
import { useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { ModeSwitch, MyTurn, Notice, StopAll } from "@/components/ControlBar"
import { Lamp } from "@/components/Lamp"
import { TicketSheet } from "@/components/TicketSheet"
import { useOverview } from "@/hooks/queries"
import { post } from "@/lib/api"
import { money } from "@/lib/format"
import { useTheme } from "@/lib/theme"
import { cn } from "@/lib/utils"

const NAV = [
  { to: "/", label: "Ora", icon: LayoutDashboard, end: true },
  { to: "/tickets", label: "Ticket", icon: Ticket },
  { to: "/runs", label: "Esecuzioni", icon: Activity },
  { to: "/repo", label: "Repo", icon: GitBranch },
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
  return (
    <span className="flex items-center gap-2 text-sm">
      <Lamp kind={n ? "violet" : "idle"} live={n > 0} />
      {n ? `${n} ${n === 1 ? "agente al lavoro" : "agenti al lavoro"}` : "Nessun agente al lavoro"}
    </span>
  )
}

export function Shell() {
  const { setTheme } = useTheme()
  const qc = useQueryClient()
  const logout = async () => {
    await post("/api/auth/logout", {})
    qc.clear()
    window.location.assign("/")
  }
  const dark = document.documentElement.classList.contains("dark")

  return (
    <div className="min-h-screen md:grid md:grid-cols-[208px_1fr]">
      <aside className="border-b bg-card md:sticky md:top-0 md:h-screen md:border-b-0 md:border-r">
        <div className="flex items-center gap-2 px-4 py-4">
          <BookOpenCheck className="size-5 text-primary" aria-hidden />
          <span className="font-display text-xl font-semibold">autodev</span>
        </div>
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
