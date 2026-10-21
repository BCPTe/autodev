import { useQuery } from "@tanstack/react-query"
import { api, type Comment, type ProjectInfo, type DiffFile, type Pr, type Interactive, type TicketAction, type Config, type Costs, type Overview, type RepoState, type Run, type RunEvent, type Ticket } from "@/lib/api"

export const useOverview = () =>
  useQuery({ queryKey: ["overview"], queryFn: () => api<Overview>("/api/overview"), refetchInterval: 5000 })

export const useTickets = () =>
  useQuery({ queryKey: ["tickets"], queryFn: () => api<{ tickets: Ticket[]; fetched_at: number }>("/api/tickets"), refetchInterval: 20000 })

export const useTicket = (id: string | null) =>
  useQuery({
    queryKey: ["ticket", id],
    enabled: !!id,
    queryFn: () => api<{ ticket: Ticket; comments: Comment[]; runs: Run[]; actions: TicketAction[] }>(`/api/tickets/${id}`),
  })

export const useRuns = () =>
  useQuery({ queryKey: ["runs"], queryFn: () => api<{ runs: Run[] }>("/api/runs?limit=100"), refetchInterval: 4000 })

export const useRun = (id: number) =>
  useQuery({
    queryKey: ["run", id],
    queryFn: () => api<{ run: Run; events: RunEvent[]; interactive: Interactive }>(`/api/runs/${id}`),
    refetchInterval: (q) => (q.state.data?.run.status === "running" ? 2000 : false),
  })

export const useRepo = () =>
  useQuery({ queryKey: ["repo"], queryFn: () => api<RepoState>("/api/repo"), refetchInterval: 10000 })

export const useCosts = () =>
  useQuery({ queryKey: ["costs"], queryFn: () => api<Costs>("/api/costs"), refetchInterval: 15000 })

export const useConfig = () => useQuery({ queryKey: ["config"], queryFn: () => api<Config>("/api/config") })

export const usePrs = () =>
  useQuery({ queryKey: ["prs"], queryFn: () => api<{ enabled: boolean; prs: Pr[] }>("/api/prs"), refetchInterval: 30000, retry: 0 })

export const useDiff = (branch: string | null, open: boolean) =>
  useQuery({
    queryKey: ["diff", branch],
    enabled: open,
    queryFn: () => api<{ files: DiffFile[] }>(`/api/repo/diff${branch ? `?branch=${encodeURIComponent(branch)}` : ""}`),
  })

export const useProjects = () =>
  useQuery({
    queryKey: ["projects"],
    queryFn: () => api<{ default: string; projects: ProjectInfo[] }>("/api/projects"),
    refetchInterval: 10000,
  })
