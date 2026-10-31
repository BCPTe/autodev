import { useState, useSyncExternalStore } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { Activity, CircleDollarSign, GitBranch, GitPullRequest, LayoutDashboard, ChevronDown, Lightbulb, LogOut, Menu, Moon, RotateCw, Settings, Sun, Ticket } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DropdownMenu,DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { ModeSwitch, MyTurn, Notice, StopAll } from "@/components/ControlBar";
import { Lamp } from "@/components/Lamp";
import { useOverview, useProjects } from "@/hooks/queries";
import { useAct } from "@/hooks/useAct";
import { useAttention } from "@/hooks/useAttention";
import { useProjectEvents } from "@/hooks/useProjectEvents";
import { getProject, post, setProject } from "@/lib/api";
import { money } from "@/lib/format";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";
import bg from "@/assets/bg.webp";
import logo from "@/assets/logo.webp";
import bgDark from "@/assets/bg-dark.webp";

/** What a person needs day to day; everything else is a tool for looking deeper. */
const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/tickets", label: "Tickets", icon: Ticket },
  { to: "/settings", label: "Settings", icon: Settings },
];
const TOOLS = [
  { to: "/runs", label: "Activity", icon: Activity },
  { to: "/prs", label: "Pull requests", icon: GitPullRequest },
  { to: "/repo", label: "Repo", icon: GitBranch },
  { to: "/learnings", label: "Learnings", icon: Lightbulb },
  { to: "/costs", label: "Costs", icon: CircleDollarSign },
];

function NavItem({ to, label, icon: Icon, end, small }: { to: string; label: string; icon: typeof Ticket; end?: boolean; small?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-3 whitespace-nowrap rounded-lg px-3 py-2 text-muted-foreground hover:bg-muted hover:text-foreground",
          small && "py-1.5 text-[13.5px]",
          isActive && "bg-accent font-medium text-accent-foreground hover:bg-accent",
        )
      }>
      <Icon className={small ? "size-3.5" : "size-4"} aria-hidden />
      {label}
    </NavLink>
  );
}

function Budget() {
  const { data } = useOverview();
  if (!data) return null;
  const pct = Math.min(100, (data.spent_today / data.daily_cap) * 100);
  const hot = pct >= 80;
  return (
    <div className="flex items-center gap-3 border px-3 py-1.5 rounded-full inset-shadow-sm sm:px-4" title="Today's spend against the daily cap">
      <span className="hidden text-xs text-muted-foreground xl:inline">Today</span>
      <span className={cn("font-display text-base tabular-nums", hot && "max-sm:text-lamp-red")}>
        {money(data.spent_today)} <span className="text-muted-foreground">/ {money(data.daily_cap)}</span>
      </span>
      <div
        role="progressbar"
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Daily budget"
        className="hidden h-1.5 w-20 overflow-hidden rounded-full bg-muted sm:block">
        <div className={cn("h-full", hot ? "bg-lamp-red" : "bg-primary")} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function Agents() {
  const { data } = useOverview();
  const n = data?.running.length ?? 0;
  const asks = data?.approvals.length ?? 0;
  return (
    <span className="flex items-center gap-3 text-sm">
      {n ? (
        <DropdownMenu>
          <DropdownMenuTrigger className="flex items-center gap-2 bg-muted rounded-full px-3 sm:px-4 py-1.5 inset-shadow-sm text-sm text-muted-foreground">
            <Lamp kind="violet" live />
            {n}
            <span className="max-sm:hidden">{n === 1 ? "agent working" : "agents working"}</span>
            <span className="sm:hidden">working</span>
            <ChevronDown className="size-3.5 text-muted-foreground" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-72">
            {data?.running.map((r) => (
              <DropdownMenuItem key={r.id} asChild>
                <Link to={`/runs/${r.id}`} className="flex flex-col items-start gap-0.5">
                  <span className="w-full truncate font-medium">{r.ticket_title}</span>
                  <span className="text-xs text-muted-foreground">
                    {r.ticket_id} · {r.kind}
                  </span>
                </Link>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : (
        <span className="flex items-center gap-2 bg-muted rounded-full px-3 sm:px-4 py-1.5 inset-shadow-sm text-sm text-muted-foreground">
          <Lamp kind="idle" />
          <span className="max-sm:hidden">No agent working</span>
          <span className="sm:hidden">Idle</span>
        </span>
      )}
      {asks > 0 && (
        <Link to="/" className="bg-lamp-amber/25 text-sm font-medium border px-4 py-1.5 rounded-full inset-shadow-sm">
          {asks} <span className="max-sm:hidden">{asks === 1 ? "request waiting" : "requests waiting"}</span>
          <span className="sm:hidden">waiting</span>
        </Link>
      )}
    </span>
  );
}

// one shared clock, ticking every second, so render never reads Date.now() itself
let clockNow = Date.now();
const clockSubscribe = (notify: () => void) => {
  const t = setInterval(() => {
    clockNow = Date.now();
    notify();
  }, 1000);
  return () => clearInterval(t);
};
const clockSnapshot = () => clockNow;

function NextCheck() {
  const { data } = useOverview();
  const { act, pending } = useAct();
  const now = useSyncExternalStore(clockSubscribe, clockSnapshot);
  const next = data?.control.next_check ?? null;
  if (next === null) return null;
  const left = Math.max(0, Math.ceil(next - now / 1000));
  return (
    <span className="flex items-center gap-1.5 text-sm text-muted-foreground" title="Time until the next check of the open tickets">
      <span className="max-sm:hidden">Next check</span>{" "}
      {left > 0 ? (
        <span className="tabular-nums text-foreground">
          {Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")}
        </span>
      ) : (
        "in progress…"
      )}
      <Button
        variant="ghost"
        size="icon"
        className="size-6"
        title="Check now"
        aria-label="Check now"
        disabled={pending || left === 0}
        onClick={() => act(() => post("/api/control/check-now", {}))}>
        <RotateCw className={cn("size-3.5", pending && "animate-spin motion-reduce:animate-none")} aria-hidden />
      </Button>
    </span>
  );
}

function ProjectSwitch() {
  const { data } = useProjects();
  if (!data || data.projects.length < 2) return null;
  const current = getProject();
  return (
    <div className="mx-3 mb-3 mt-2">
      <p className="px-1 pb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">Project</p>
      <Select
        value={current ?? data.default}
        onValueChange={(v) => {
          setProject(v);
          window.location.assign("/");
        }}>
        <SelectTrigger aria-label="Project">
          <SelectValue />
        </SelectTrigger>
        <SelectContent side="top">
          {data.projects.map((p) => (
            <SelectItem key={p.name} value={p.name}>
              {p.name}
              {p.waiting ? ` · ${p.waiting} waiting` : p.running ? " · working" : ""}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

/** Theme and sign-out: on phones they sit in the first row, elsewhere at the end of the controls. */
function HeaderIcons({ className }: { className?: string }) {
  const { dark, setTheme } = useTheme();
  const qc = useQueryClient();
  const logout = async () => {
    await post("/api/auth/logout", {});
    qc.clear();
    window.location.assign("/");
  };
  return (
    <div className={cn("flex items-center gap-1", className)}>
      <Button variant="ghost" size="icon" radius="full" aria-label={dark ? "Switch to light theme" : "Switch to dark theme"} onClick={() => setTheme(dark ? "light" : "dark")}>
        {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
      </Button>
      <Button variant="ghost" size="icon" radius="full" aria-label="Sign out" onClick={logout}>
        <LogOut className="size-4" />
      </Button>
    </div>
  );
}

function Sidebar() {
  return (
    <div className="flex min-h-full flex-1 flex-col">
      <div className="flex items-center gap-4 px-4 py-4">
        <img src={logo} alt="" className="size-12" />
        <span className="font-mono text-2xl font-semibold">AutoDev</span>
      </div>
      <nav className="flex flex-1 flex-col gap-1 px-2 pb-2" aria-label="Sections">
        {NAV.map((item) => (
          <NavItem key={item.to} {...item} />
        ))}
        <p className="px-3 pb-1 pt-4 text-xs font-medium uppercase tracking-wide text-muted-foreground">Tools</p>
        {TOOLS.map((item) => (
          <NavItem key={item.to} {...item} small />
        ))}
      </nav>
      <ProjectSwitch />
    </div>
  );
}

export function Shell() {
  useAttention();
  useProjectEvents();
  const { pathname } = useLocation();
  // the ticket page works side by side (decisions | live run or diff), so it uses the full width
  const { dark } = useTheme();
  // below lg the sidebar is a drawer; following a link closes it
  // remember the page it was opened on: navigating elsewhere closes it without an effect
  const [openOn, setOpenOn] = useState<string | null>(null);
  const drawer = openOn === pathname;
  const setDrawer = (open: boolean) => setOpenOn(open ? pathname : null);

  return (
    <div
      className="flex h-dvh flex-col overflow-hidden bg-cover bg-center lg:grid lg:grid-cols-[280px_minmax(0,1fr)] lg:grid-rows-[minmax(0,1fr)]"
      style={{ backgroundImage: `url(${dark ? bgDark : bg})` }}>
      <aside className="hidden rounded-xl border bg-card/30 shadow-md backdrop-blur-xs select-none lg:m-3 lg:flex lg:flex-col lg:overflow-y-auto">
        <Sidebar />
      </aside>
      <Sheet open={drawer} onOpenChange={setDrawer}>
        <SheetContent
          side="left"
          onOpenAutoFocus={(e) => {
            e.preventDefault();
            (e.currentTarget as HTMLElement).focus();
          }}
          className="w-[min(300px,85vw)] gap-0 overflow-y-auto border-r bg-white backdrop-blur-xl lg:hidden">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <SheetDescription className="sr-only">Sections and tools</SheetDescription>
          <Sidebar />
        </SheetContent>
      </Sheet>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="z-20 mx-3 mt-3 flex shrink-0 flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border bg-card/30 px-3 py-2.5 shadow-md backdrop-blur-xs select-none sm:gap-x-4 xl:gap-x-6 sm:px-6 lg:ml-0">
          <Button variant="ghost" size="icon" radius="full" className="-ml-1 lg:hidden" aria-label="Open navigation" aria-expanded={drawer} onClick={() => setDrawer(true)}>
            <Menu className="size-5" />
          </Button>
          <Link to="/" className="flex items-center gap-2 lg:hidden" aria-label="AutoDev, dashboard">
            <img src={logo} alt="" className="size-8" />
            <span className="hidden font-mono text-lg font-semibold sm:inline md:hidden">AutoDev</span>
          </Link>
          {/* phones: the groups dissolve into the header's rows: logo, agents and icons, then spend and checkout, then the autonomy switch */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 max-sm:contents xl:gap-x-6">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2 max-sm:order-1 sm:contents">
              <Agents />
              <NextCheck />
            </div>
            <div className="max-sm:order-5">
              <Budget />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 max-sm:contents sm:ml-auto xl:gap-x-6">
            {/* phones: checkout stays beside the spend; Stop all, shown only while agents run, wraps below */}
            <div className="flex flex-row-reverse items-center gap-4 max-sm:contents xl:gap-6">
              <div className="max-sm:order-5">
                <MyTurn />
              </div>
              <div className="empty:hidden max-sm:order-5">
                <StopAll />
              </div>
            </div>
            <div className="max-sm:order-6 max-sm:w-full">
              <ModeSwitch />
            </div>
            <HeaderIcons className="max-sm:hidden" />
          </div>
          <HeaderIcons className="ml-auto max-sm:order-1 sm:hidden" />
          <span aria-hidden className="basis-full max-sm:order-4 sm:hidden" />
        </header>
        <Notice />
        <div className="mx-3 mb-3 mt-3 min-h-0 min-w-0 flex-1 overflow-y-auto rounded-xl border bg-card/30 shadow-md backdrop-blur-xs lg:ml-0">
          <main className="px-4 py-6 sm:px-8 sm:py-8">
            <div key={pathname} className="page-in">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
