export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export const UNAUTHORIZED_EVENT = "autodev:unauthorized"

const PROJECT_KEY = "autodev:project"
let currentProject: string | null = null

export function getProject(): string | null {
  return currentProject
}

/** Remembers which project the dashboard is showing; every project-scoped call is routed to it. */
export function setProject(name: string) {
  currentProject = name
  try {
    localStorage.setItem(PROJECT_KEY, name)
  } catch {
    /* private mode: the default project is used next time */
  }
}

export function storedProject(): string | null {
  try {
    return localStorage.getItem(PROJECT_KEY)
  } catch {
    return null
  }
}

/** /api/overview -> /api/p/<project>/overview; auth and project-list calls stay global. */
export function scoped(path: string): string {
  if (!currentProject || !path.startsWith("/api/") || path.startsWith("/api/auth/") || path.startsWith("/api/projects") || path.startsWith("/api/p/")) return path
  return `/api/p/${encodeURIComponent(currentProject)}/${path.slice("/api/".length)}`
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(scoped(path), {
    credentials: "same-origin",
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  })
  if (res.status === 401 && !path.startsWith("/api/auth/")) window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* body is not JSON */
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail))
  }
  return res.json() as Promise<T>
}

export const post = <T,>(path: string, body: unknown) => api<T>(path, { method: "POST", body: JSON.stringify(body) })
export const put = <T,>(path: string, body: unknown) => api<T>(path, { method: "PUT", body: JSON.stringify(body) })
export const patch = <T,>(path: string, body: unknown) => api<T>(path, { method: "PATCH", body: JSON.stringify(body) })

export interface ProjectInfo {
  name: string
  repo: string
  mode: Mode
  running: number
  waiting: number
}

export type Mode = "auto" | "supervised" | "manual" | "paused"

export interface Control {
  mode: Mode
  modes: Mode[]
  my_turn: boolean
  my_turn_since: number | null
  busy: boolean
  daily_cap: number
  spent_today: number
  blocked: string | null
  auto_approve_risks: string[]
  poll_seconds: number
  next_check: number | null
  quiet_hours: string | null
  quiet: boolean
  notifications: boolean
  can_notify: boolean
  permission_policy: "ask" | "trusted"
}

export interface TicketAction {
  ts: number
  actor: "user" | "auto"
  action: string
  detail: string
}

export type TicketState = "new" | "needs_info" | "analyzed" | "in_progress" | "review" | "escalated" | "closed"

export interface Ticket {
  id: string
  title: string
  status: TicketState
  kind: string | null
  area: string | null
  priority: string | null
  environment: string | null
  page_url: string | null
  reported_by: string | null
  authorized: boolean
  attempts: number
  cost_usd: number
  model: string | null
  url: string | null
  risk: string | null
  branch: string | null
  pr_url: string | null
  agent_note: string | null
  verification: string | null
  created_at: string | null
  updated_at: string | null
  body?: string
  last_run?: { kind: string; status: string; outcome: string | null; started_at: number } | null
}

export interface Comment {
  author: string
  is_bot: boolean
  text: string
  created_at: string | null
}

export interface Run {
  id: number
  project: string
  ticket_id: string
  ticket_title: string
  kind: "triage" | "fix" | "checks" | "publish"
  status: "running" | "done" | "failed" | "cancelled"
  model: string | null
  started_at: number
  finished_at: number | null
  duration: number
  cost_usd: number
  outcome: string | null
  branch: string | null
  pr_url: string | null
  error: string | null
  cancel_requested: boolean
}

export interface RunEvent {
  id: number
  ts: number
  type: "started" | "log" | "result" | "finished" | "error" | "cancelled" | "user" | "agent" | "paused" | "permission" | "checkpoint" | "decision"
  text: string
  data: Record<string, unknown> | null
}

export interface InboxItem {
  kind: "ticket"
  state: TicketState
  ticket: Pick<Ticket, "id" | "title" | "status" | "area" | "priority" | "risk" | "url" | "pr_url" | "branch" | "agent_note" | "updated_at">
}

export interface Approval {
  id: number
  run_id: number
  kind: "permission" | "checkpoint"
  title: string
  detail: { tool?: string; input?: Record<string, unknown>; name?: string; files?: string[]; summary?: string; notes?: string; checks?: string[]; risk?: string }
  created_at: number
  ticket_id: string
  ticket_title: string
  run_kind: "triage" | "fix" | "checks" | "publish"
}

export interface Interactive {
  live: boolean
  state: "running" | "waiting" | "approval" | null
  approvals: Approval[]
}

export interface Overview {
  project: string
  spent_today: number
  daily_cap: number
  ticket_cap: number
  counts: Partial<Record<TicketState, number>>
  running: Run[]
  recent_problems: Run[]
  inbox: InboxItem[]
  repo: { branch: string; clean: boolean; on_agent_branch: boolean }
  control: Control
  approvals: Approval[]
}

export interface Costs {
  today: number
  daily_cap: number
  ticket_cap: number
  total: number
  by_day: { day: string; cost: number; runs: number }[]
  by_model: { model: string; cost: number; runs: number }[]
  by_kind: { kind: string; cost: number; runs: number }[]
  by_ticket: { ticket_id: string; title: string; cost: number; runs: number }[]
}

export interface RepoState {
  path: string
  base_branch: string
  branch: string
  on_agent_branch: boolean
  dirty: string[]
  clean: boolean
  ahead: number | null
  behind: number | null
  busy: boolean
  branches: { name: string; merged: boolean; current: boolean; last_commit: string; updated: string; ahead: number }[]
  commits: { sha: string; subject: string }[]
}

export interface Pr {
  number: number
  title: string
  url: string
  branch: string
  state: "open" | "closed" | "merged"
  draft: boolean
  body: string
  updated_at: string
  author: string
  checks: { verdict: "none" | "passing" | "failing" | "pending" | "unknown"; total: number; failed: number; pending: number; reason?: string; note?: string } | null
  mergeable: boolean | null
  ticket: Pick<Ticket, "id" | "title" | "risk" | "verification" | "agent_note" | "status"> | null
}

export interface DiffFile {
  path: string
  additions: number | null
  deletions: number | null
  patch: string
  truncated: boolean
}

export interface Config {
  project: string
  repo: string
  base_branch: string
  local_path: string
  workspace_mode: string
  limits: { max_attempts: number; max_files: number; budget_usd_per_ticket: number; daily_budget_usd: number; max_fix_runs: number }
  agents: Record<string, { models: string[]; max_turns: number }>
  model_choices: Record<string, string>
  pr_enabled: boolean
  has_checks: boolean
  never_automerge: string[]
  daily_cap_effective: number
  autonomy: { default_mode: Mode; poll_seconds: number; retry_cooldown_seconds: number; auto_approve_risks: string[]; permission_policy: "ask" | "trusted"; checkpoints: ("after_agent" | "before_pr")[] }
}
