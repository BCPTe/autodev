import { useState } from "react";
import { Check, Copy, GitBranch } from "lucide-react";
import { cn } from "@/lib/utils";
import { Link, useNavigate } from "react-router-dom";
import { PageHeader } from "@/components/PageHeader";
import { PipelineRail } from "@/components/PipelineRail";
import { RunFeed } from "@/components/RunFeed";
import { ApprovalCard } from "@/components/ApprovalCard";
import { TicketActionCard } from "@/components/NeedsYouCards";
import { hasActionCard } from "@/components/needs-you-state";
import { Button } from "@/components/ui/button";
import { Lamp } from "@/components/Lamp";
import { useAct } from "@/hooks/useAct";
import { post } from "@/lib/api";
import { StopRun } from "@/components/StopRun";
import { Skeleton } from "@/components/ui/skeleton";
import { useOverview, useRuns, useTickets } from "@/hooks/queries";
import { useNow } from "@/hooks/useNow";
import { ago, duration, money, shortModel } from "@/lib/format";
import { KIND_LABEL, RUN_LAMP, STATES } from "@/lib/status";
import type { Run, TicketState } from "@/lib/api";

const ORDER: TicketState[] = ["escalated", "review", "analyzed", "needs_info"];

function DismissRun({ runId }: { runId: number }) {
  const { act } = useAct();
  return (
    <Button size="xs" variant="ghost" className="mt-3" title="Hide this problem; the run stays in Activity" onClick={() => act(() => post(`/api/runs/${runId}/dismiss`, {}))}>
      Dismiss
    </Button>
  );
}

function Elapsed({ run }: { run: Run }) {
  const now = useNow(1000);
  return <span className="tabular-nums">{duration(now / 1000 - run.started_at)}</span>;
}

function BranchPill({ branch, clean }: { branch: string; clean: boolean }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard?.writeText(branch).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      },
      () => {},
    );
  };
  return (
    <span className="flex flex-wrap items-center gap-2">
      <span className="select-none">On active branch:</span>
      <span className="inline-flex min-w-0 items-center gap-3 rounded-full inset-shadow-sm border bg-card px-2.5 py-1 font-mono text-[13px] text-foreground">
        <GitBranch className="size-4 shrink-0 text-primary ml-1.5" />
        <span className="truncate">{branch}</span>
        <button type="button" onClick={copy} title="Copy branch name" aria-label="Copy branch name" className="rounded-full p-1.5 hover:bg-muted">
          {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
        </button>
      </span>
      {!clean && <span>· uncommitted changes</span>}
    </span>
  );
}

function LastRunTerminal({ run }: { run: Run }) {
  const tools = new Map<string, number>();
  for (const s of run.sessions ?? []) for (const [t, n] of Object.entries(s.tools)) tools.set(t, (tools.get(t) ?? 0) + n);
  const toolLine = [...tools]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([t, n]) => `${t}×${n}`)
    .join(" ");
  const turns = (run.sessions ?? []).reduce((a, s) => a + s.turns, 0);
  const ok = run.status === "done";
  const rows: [string, string | null | undefined, string?][] = [
    ["status", run.status, ok ? "text-emerald-400" : run.status === "failed" ? "text-red-400" : "text-amber-400"],
    ["model", run.model ? shortModel(run.model) : null],
    ["took", `${duration(run.duration)} · ${money(run.cost_usd)}${turns ? ` · ${turns} turns` : ""}`],
    ["tools", toolLine || null],
    ["branch", run.branch],
    ["pr", run.pr_url],
    ["outcome", run.outcome],
    ["error", run.error, "text-red-400"],
  ];
  return (
    <div className="mt-3 overflow-hidden rounded-md border border-white/10 bg-[#0d1117]/85 backdrop-blur-sm font-mono text-[12.5px] leading-6 text-slate-300">
      <div className="flex items-center gap-1.5 border-b border-white/10 px-3 py-2">
        <span className="size-2.5 rounded-full bg-red-400/70" />
        <span className="size-2.5 rounded-full bg-amber-400/70" />
        <span className="size-2.5 rounded-full bg-emerald-400/70" />
        <span className="ml-2 text-xs text-slate-500 select-none">last run · {ago(run.finished_at ?? run.started_at)}</span>
      </div>
      <div className="space-y-0.5 p-3">
        <p className="truncate">
          <span className="text-emerald-400">$</span> autodev {run.kind}{" "}
          <Link className="text-sky-300 underline-offset-4 hover:underline" to={`/runs/${run.id}`}>
            #{run.id}
          </Link>{" "}
          <span className="text-slate-500"># {run.ticket_title}</span>
        </p>
        {rows
          .filter(([, v]) => v)
          .map(([k, v, c]) => (
            <p key={k} className="flex gap-3">
              <span className="w-16 shrink-0 text-slate-500">{k}</span>
              <span className={cn("min-w-0 break-words", c)}>{v}</span>
            </p>
          ))}
        <p>
          <span className="text-emerald-400">$</span> <span className="animate-pulse">▍</span>
        </p>
      </div>
    </div>
  );
}

export function Now() {
  const { data: tickets, error: ticketsError } = useTickets();
  const { data: overview } = useOverview();
  const { data: runs } = useRuns();
  const navigate = useNavigate();
  const open = (id: string) => navigate(`/tickets/${id}`);

  const sorted = [...(overview?.dashboard ?? [])].sort((a, b) => ORDER.indexOf(a.state) - ORDER.indexOf(b.state));
  const cards = sorted.filter((i) => hasActionCard(i.state));
  const dashboard = sorted.filter((i) => !hasActionCard(i.state));
  const problems = overview?.recent_problems ?? [];
  const last = runs?.runs.find((r) => r.status !== "running");

  return (
    <>
      <PageHeader title="Dashboard">{overview?.repo && <BranchPill branch={overview.repo.branch} clean={overview.repo.clean} />}</PageHeader>

      {tickets ? (
        <PipelineRail tickets={tickets.tickets} />
      ) : ticketsError ? (
        <div role="alert" className="rounded-xl border border-lamp-red/40 bg-lamp-red/10 p-4 text-sm">
          <p className="font-medium">Could not load the tickets for this project</p>
          <p className="mt-1 break-words text-muted-foreground">{ticketsError.message}</p>
        </div>
      ) : (
        <Skeleton className="min-h-[50vh] w-full" />
      )}

      <div className="mt-14 grid gap-12 lg:grid-cols-[minmax(0,5fr)_minmax(0,4fr)]">
        <section aria-labelledby="needs-you">
          <h2 id="needs-you" className="section-title">
            Needs you
          </h2>
          {overview && overview.approvals.length > 0 && (
            <div className={cn("space-y-3", dashboard.length + problems.length > 0 ? "mb-4" : "border-b pb-4")}>
              {overview.approvals.map((a) => (
                <ApprovalCard key={a.id} a={a} />
              ))}
            </div>
          )}
          {cards.length > 0 && (
            <div className={cn("space-y-3", dashboard.length + problems.length > 0 ? "mb-4" : "")}>
              {cards.map((i) => (
                <TicketActionCard key={i.ticket.id} item={i} />
              ))}
            </div>
          )}
          {overview && dashboard.length === 0 && cards.length === 0 && problems.length === 0 && overview.approvals.length === 0 && (
            <div className="py-3">
              <p className="text-muted-foreground">Nothing needs you right now.</p>
            </div>
          )}
          {dashboard.length + problems.length > 0 && (
            <ul className="divide-y">
              {problems.map((r) => (
                <li key={`run-${r.id}`} className="flex items-start gap-2 hover:bg-muted/30">
                  <Link to={`/runs/${r.id}`} className="flex min-w-0 flex-1 items-start gap-3 py-3">
                    <Lamp kind={RUN_LAMP[r.status]} className="mt-1.5" />
                    <div className="min-w-0">
                      <p className="truncate font-medium">
                        {KIND_LABEL[r.kind]} {r.status === "failed" ? "failed" : "stopped"}: {r.ticket_title}
                      </p>
                      <p className="truncate text-[13px] text-muted-foreground">{r.error ?? "No error message. Open the run for details."}</p>
                    </div>
                    <span className="ml-auto whitespace-nowrap text-xs text-muted-foreground">{ago(r.started_at)}</span>
                  </Link>
                  <DismissRun runId={r.id} />
                </li>
              ))}
              {dashboard.map(({ ticket, state }) => (
                <li key={ticket.id}>
                  <button onClick={() => open(ticket.id)} className="flex w-full items-start gap-3 px-3 py-3 text-left hover:bg-muted/50">
                    <Lamp kind={STATES[state].lamp} className="mt-1.5" />
                    <div className="min-w-0">
                      <p className="truncate font-medium">{ticket.title}</p>
                      <p className="truncate text-[13px] text-muted-foreground">
                        {STATES[state].label}: {STATES[state].hint}
                      </p>
                    </div>
                    <span className="ml-auto whitespace-nowrap text-xs text-muted-foreground">{ago(ticket.updated_at)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section aria-labelledby="running-now">
          <h2 id="running-now" className="section-title">
            Running now
          </h2>
          {overview && overview.running.length === 0 && (
            <div className="py-3">
              <p className="text-muted-foreground select-none">No agent is running.</p>
              {last && <LastRunTerminal run={last} />}
            </div>
          )}
          <div className="space-y-6">
            {overview?.running.map((r) => (
              <article key={r.id}>
                <header className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1">
                  <Lamp kind="violet" live />
                  <Link to={`/runs/${r.id}`} className="font-medium underline-offset-4 hover:underline">
                    {KIND_LABEL[r.kind]}: {r.ticket_title}
                  </Link>
                  <span className="text-[13px] text-muted-foreground">
                    {shortModel(r.model)} · <Elapsed run={r} />
                  </span>
                  <span className="ml-auto">
                    <StopRun run={r} />
                  </span>
                </header>
                <RunFeed runId={r.id} className="h-80" />
              </article>
            ))}
          </div>
        </section>
      </div>
    </>
  );
}
