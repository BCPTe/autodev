import { PageHeader } from "@/components/PageHeader"
import { Skeleton } from "@/components/ui/skeleton"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useConfig, useOverview } from "@/hooks/queries"
import { useAct } from "@/hooks/useAct"
import { put } from "@/lib/api"
import { browserNotificationsOn, setBrowserNotifications } from "@/hooks/useAttention"
import { MODES } from "@/components/ControlBar"
import { money, shortModel } from "@/lib/format"

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 border-b py-2.5 sm:grid-cols-[14rem_1fr]">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  )
}

function DailyCap({ current }: { current: number }) {
  const { act, pending } = useAct()
  const [value, setValue] = useState(String(current))
  const n = Number(value)
  const valid = Number.isFinite(n) && n > 0 && n <= 1000
  return (
    <form className="flex items-center gap-2" onSubmit={(e) => { e.preventDefault(); if (valid) act(() => put("/api/control", { daily_budget_usd: n }), "Daily cap updated") }}>
      <span aria-hidden>$</span>
      <Input aria-label="Daily cap in dollars" className="h-8 w-24" inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} />
      <Button type="submit" size="sm" variant="outline" disabled={pending || !valid || n === current}>Save</Button>
    </form>
  )
}

function QuietHours({ current }: { current: string | null }) {
  const { act, pending } = useAct()
  const [value, setValue] = useState(current ?? "")
  const valid = value === "" || /^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d$/.test(value)
  return (
    <form className="flex flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); if (valid) act(() => put("/api/control", { quiet_hours: value }), value ? "Quiet hours saved" : "Quiet hours removed") }}>
      <Input aria-label="Quiet hours" className="h-8 w-36 font-mono" placeholder="22:00-07:00" value={value} onChange={(e) => setValue(e.target.value)} />
      <Button type="submit" size="sm" variant="outline" disabled={pending || !valid || value === (current ?? "")}>Save</Button>
      <span className="text-xs text-muted-foreground">Empty = always on. In these hours nothing starts by itself.</span>
    </form>
  )
}

function Notifications({ server, canNotify }: { server: boolean; canNotify: boolean }) {
  const { act, pending } = useAct()
  const [browser, setBrowser] = useState(browserNotificationsOn())
  return (
    <div className="space-y-2">
      <label className="flex items-center gap-2">
        <input type="checkbox" className="size-4 accent-[var(--primary)]" checked={server} disabled={pending || !canNotify} onChange={(e) => act(() => put("/api/control", { notifications: e.target.checked }), e.target.checked ? "Desktop notifications on" : "Desktop notifications off")} />
        Desktop notifications {!canNotify && <span className="text-xs text-muted-foreground">(needs <code>notify-send</code> or <code>autonomy.notify_command</code>)</span>}
      </label>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          className="size-4 accent-[var(--primary)]"
          checked={browser}
          onChange={async (e) => setBrowser(await setBrowserNotifications(e.target.checked))}
        />
        Browser notifications <span className="text-xs text-muted-foreground">(only while the tab is open in the background)</span>
      </label>
    </div>
  )
}

export function Settings() {
  const { data: c, isLoading } = useConfig()
  const { data: overview } = useOverview()
  if (isLoading || !c) return <Skeleton className="h-64 w-full" />
  const control = overview?.control

  return (
    <>
      <PageHeader title="Impostazioni">Autonomy, quiet hours and the daily cap are changed here; everything else in <span className="font-mono">projects/{c.project}.yaml</span></PageHeader>

      <section className="max-w-3xl">
        <h2 className="mb-1 text-xl font-semibold">Autonomy</h2>
        <dl>
          <Row label="Mode">{MODES.find((m) => m.id === control?.mode)?.label}: <span className="text-muted-foreground">{MODES.find((m) => m.id === control?.mode)?.hint}</span></Row>
          <Row label="Automatic approval">Only {c.autonomy.auto_approve_risks.join(" and ")} risk (in Auto mode)</Row>
          <Row label="Check frequency">Every {c.autonomy.poll_seconds} seconds (in Auto and Supervised)</Row>
          <Row label="Retry after an error">After {Math.round(c.autonomy.retry_cooldown_seconds / 60)} minutes, or by hand</Row>
          <Row label="Pauses for your approval">{c.autonomy.checkpoints.length ? c.autonomy.checkpoints.map((k) => (k === "after_agent" ? "after the agent, before verification" : "before the pull request")).join("; ") + " (not in Auto mode)" : "None"}</Row>
          <Row label="Quiet hours">{control && <QuietHours key={control.quiet_hours ?? ""} current={control.quiet_hours} />}</Row>
          <Row label="Notifications">{control && <Notifications server={control.notifications} canNotify={control.can_notify} />}</Row>
          <Row label="Daily cap"><DailyCap key={c.daily_cap_effective} current={c.daily_cap_effective} /></Row>
        </dl>

        <h2 className="mb-1 mt-10 text-xl font-semibold">Project</h2>
        <dl>
          <Row label="Repository">{c.repo}</Row>
          <Row label="Base branch">{c.base_branch}</Row>
          <Row label="Cartella locale"><span className="font-mono text-[13px]">{c.local_path}</span></Row>
          <Row label="Where the agent works">{c.workspace_mode === "inplace" ? "In the project's checkout, on a dedicated branch" : "In a separate clone"}</Row>
          <Row label="Automatic pull requests">{c.pr_enabled ? "On" : "Off"}</Row>
        </dl>

        <h2 className="mb-1 mt-10 text-xl font-semibold">Limits</h2>
        <dl>
          <Row label="Cap per ticket">{money(c.limits.budget_usd_per_ticket)}</Row>
          <Row label="Attempts per start">{c.limits.max_attempts}</Row>
          <Row label="Fix starts per ticket">{c.limits.max_fix_runs}</Row>
          <Row label="Files a fix may change">{c.limits.max_files}</Row>
        </dl>

        <h2 className="mb-1 mt-10 text-xl font-semibold">Agents</h2>
        <dl>
          {Object.entries(c.agents).map(([name, a]) => (
            <Row key={name} label={name === "triage" ? "Triage" : "Fix"}>{a.models.map(shortModel).join(" → ")} · up to {a.max_turns} turns</Row>
          ))}
          <Row label="Models selectable in the ticket">{Object.entries(c.model_choices).map(([k, v]) => `${k} (${v})`).join(", ")}</Row>
        </dl>

        <h2 className="mb-1 mt-10 text-xl font-semibold">High-risk files</h2>
        <p className="mb-2 text-muted-foreground">Changes to these files raise the risk to High.</p>
        <ul className="font-mono text-[13px]">{c.never_automerge.map((p) => <li key={p}>{p}</li>)}</ul>
      </section>
    </>
  )
}
