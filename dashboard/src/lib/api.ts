export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export const UNAUTHORIZED_EVENT = "autodev:unauthorized"

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
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
  kind: "triage" | "fix"
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
  type: "started" | "log" | "result" | "finished" | "error" | "cancelled"
  text: string
  data: Record<string, unknown> | null
}

export interface InboxItem {
  kind: "ticket"
  state: TicketState
  ticket: Pick<Ticket, "id" | "title" | "status" | "area" | "priority" | "risk" | "url" | "pr_url" | "branch" | "agent_note" | "updated_at">
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
  never_automerge: string[]
  daily_cap_effective: number
}
