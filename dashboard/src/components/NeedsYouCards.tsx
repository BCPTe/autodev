import { useState } from "react";
import { Link } from "react-router-dom";
import { ExternalLink, GitMerge, ShieldCheck, X } from "lucide-react";
import { Dialog } from "radix-ui";
import { DiffView } from "@/components/DiffView";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Lamp } from "@/components/Lamp";
import { Level } from "@/components/Level";
import { useAct } from "@/hooks/useAct";
import { useConfig, useOverview, usePrs, useTicket } from "@/hooks/queries";
import { mergeBlocker } from "@/pages/Prs";
import { patch, post, type DashboardItem, type Pr } from "@/lib/api";
import { ago } from "@/lib/format";
import { STATES, type Lamp as LampKind } from "@/lib/status";
import type { ColorName } from "@/components/ui/colors";
import { latestUnderstanding } from "@/lib/understanding";

type Item = DashboardItem

/** Navigation and secondary links: quiet until hovered, so the one real action in the card stands out. */
const QUIET = "text-muted-foreground hover:text-foreground";

const STATE_COLOR: Record<LampKind, ColorName> = {
  green: "green",
  blue: "blue",
  amber: "amber",
  red: "red",
  violet: "violet",
  idle: "slate",
};

function CardShell({ item, children, actions }: { item: Item; children?: React.ReactNode; actions: React.ReactNode }) {
  const { ticket, state } = item;
  return (
    <article className="flex flex-col gap-4 rounded-xl border bg-card/80 hover:bg-card p-4 sm:flex-row sm:items-stretch sm:justify-between">
      <div className="min-w-0 flex-1 flex flex-col gap-3 justify-between">
        <header className="space-y-1.5">
          <Badge variant="outline" color={STATE_COLOR[STATES[state].lamp]}>
            <Lamp kind={STATES[state].lamp} className="size-2" />
            {STATES[state].label}
          </Badge>
          <Link to={`/tickets/${ticket.id}`} className="block truncate text-base font-medium underline-offset-4 hover:underline">
            {ticket.title}
          </Link>
        </header>
        {children && <div className="text-[13px]">{children}</div>}
      </div>
      <div className="flex shrink-0 flex-col gap-8 sm:items-end sm:justify-between select-none">
        <dl className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] sm:justify-end">
          {ticket.area && (
            <div className="flex items-center gap-1.5">
              <dt className="text-muted-foreground">Area</dt>
              <dd><Badge variant="secondary">{ticket.area}</Badge></dd>
            </div>
          )}
          {ticket.risk && (
            <div className="flex items-center gap-1.5">
              <dt className="text-muted-foreground">Risk</dt>
              <dd><Level value={ticket.risk} /></dd>
            </div>
          )}
          <div className="flex items-center gap-1.5">
            <dt className="text-muted-foreground">Updated</dt>
            <dd>{ago(ticket.updated_at)}</dd>
          </div>
        </dl>
        <div className="flex flex-wrap items-center gap-2 sm:justify-end">{actions}</div>
      </div>
    </article>
  );
}

/** GitHub checks as passed / failed / running counts. GitHub's summary only carries counts, not names. */
function Checks({ checks }: { checks: NonNullable<Pr["checks"]> }) {
  if (checks.verdict === "none" || checks.verdict === "unknown") {
    return (
      <p className="flex items-center gap-2 text-muted-foreground">
        <Lamp kind={checks.verdict === "none" ? "idle" : "amber"} className="size-2" />
        {checks.verdict === "none" ? "No checks on GitHub" : `Checks could not be read${checks.reason ? `: ${checks.reason}` : ""}`}
      </p>
    );
  }
  const passed = Math.max(0, checks.total - checks.failed - checks.pending);
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1" aria-label="GitHub checks">
      <li className="flex items-center gap-1.5">
        <Lamp kind="green" className="size-2" />
        {passed} passed
      </li>
      <li className="flex items-center gap-1.5">
        <Lamp kind={checks.failed ? "red" : "idle"} className="size-2" />
        {checks.failed} failed
      </li>
      {checks.pending > 0 && (
        <li className="flex items-center gap-1.5">
          <Lamp kind="amber" className="size-2" />
          {checks.pending} running
        </li>
      )}
    </ul>
  );
}

/** Projects without pull requests: fast-forward the base branch to the ticket's branch, then the ticket closes. */
export function MergeBranchButton({ ticket }: { ticket: Pick<Item["ticket"], "id" | "branch" | "risk" | "pr_url"> }) {
  const { act, pending } = useAct();
  const { data: config } = useConfig();
  const [open, setOpen] = useState(false);
  if (!config || config.pr_enabled || ticket.pr_url || !ticket.branch) return null;
  const high = ticket.risk === "High";
  const merge = async () => {
    const ok = await act(
      () => post(`/api/tickets/${ticket.id}/merge-branch`, { confirm: true }),
      (r) => `Branch merged into ${config.base_branch}; ticket closed${(r as { back_on?: string }).back_on ? `, checkout on ${(r as { back_on: string }).back_on}` : ""}`,
    );
    if (ok) setOpen(false);
  };
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Button size="sm" disabled={pending || high} title={high ? "High risk: read it and merge by hand" : `Review the changes, then fast-forward ${config.base_branch} to ${ticket.branch}`} onClick={() => setOpen(true)} leftIcon={<GitMerge />}>Merge branch</Button>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 data-[state=open]:animate-in data-[state=open]:fade-in-0" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex max-h-[88vh] w-[min(64rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col rounded-xl border bg-background shadow-xl">
          <header className="flex items-start justify-between gap-4 border-b p-4">
            <div className="min-w-0">
              <Dialog.Title className="text-lg font-semibold">Review before merging</Dialog.Title>
              <Dialog.Description className="mt-0.5 text-[13px] text-muted-foreground">
                <span className="font-mono text-xs">{ticket.branch}</span> will be fast-forwarded into <span className="font-mono text-xs">{config.base_branch}</span> and the ticket closes.
              </Dialog.Description>
            </div>
            <Dialog.Close asChild><Button size="icon" variant="ghost" aria-label="Close"><X /></Button></Dialog.Close>
          </header>
          <div className="min-h-0 flex-1 overflow-y-auto p-4"><DiffView branch={ticket.branch} /></div>
          <footer className="flex justify-end gap-2 border-t p-4">
            <Dialog.Close asChild><Button variant="outline" disabled={pending}>Cancel</Button></Dialog.Close>
            <Button loading={pending} onClick={merge} leftIcon={<GitMerge />}>Merge into {config.base_branch}</Button>
          </footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/** Review: the pull request is ready; merge it here after a confirming click. */
function ReviewCard({ item }: { item: Item }) {
  const { ticket } = item;
  const { act, pending } = useAct();
  const { data, error } = usePrs();
  const { data: config } = useConfig();
  const [armed, setArmed] = useState(false);
  const pr = data?.prs.find((p) => p.state === "open" && (p.url === ticket.pr_url || p.ticket?.id === ticket.id));
  const blocker = pr ? mergeBlocker(pr) : null;

  const merge = () => {
    if (!pr) return;
    if (!armed) {
      setArmed(true);
      setTimeout(() => setArmed(false), 4000);
      return;
    }
    setArmed(false);
    act(
      () => post(`/api/prs/${pr.number}/merge`, { confirm: true }),
      (r) => ((r as { back_on?: string | null }).back_on ? `Pull request merged; checkout back on ${(r as { back_on: string }).back_on}` : "Pull request merged"),
    );
  };

  // In review without a linked pull request: the PR was never opened (or was closed), so there is nothing to merge yet.
  const noPr = !ticket.pr_url && !pr;
  const url = pr?.url ?? ticket.pr_url;

  return (
    <CardShell
      item={item}
      actions={
        <>
          <Button asChild size="sm" variant="ghost" className={QUIET}>
            <Link to={`/tickets/${ticket.id}`}>Details</Link>
          </Button>
          {url && (
            <Button asChild size="sm" variant="ghost" className={QUIET}>
              <a href={url} target="_blank" rel="noreferrer">
                Open on GitHub <ExternalLink />
              </a>
            </Button>
          )}
          {pr && (
            <Button size="sm" disabled={pending || !!blocker} title={blocker ?? undefined} onClick={merge} leftIcon={<GitMerge />}>{armed ? "Confirm: squash and merge" : "Merge"}</Button>
          )}
          {noPr && <MergeBranchButton ticket={ticket} />}
        </>
      }>
      <div className="space-y-1.5">
        {pr?.checks && <Checks checks={pr.checks} />}
        {pr && blocker && <p className="font-medium">Merge unavailable: {blocker}</p>}
        {noPr && (
          <p className="text-muted-foreground">
            {config && !config.pr_enabled
              ? "Pull requests are off for this project: the fix was verified locally and waits on its branch. Review the changes, then merge the branch."
              : "No pull request is linked to this ticket."}
          </p>
        )}
        {!noPr && !pr && error && <p className="text-muted-foreground">GitHub could not be reached, so the pull request cannot be shown.</p>}
        {!noPr && !pr && !error && <p className="text-muted-foreground">{data ? "The pull request is no longer open." : "Loading pull request…"}</p>}
      </div>
    </CardShell>
  );
}

/** Analysed: show what autodev understood, approve it and start the fix in one click. */
function AnalyzedCard({ item }: { item: Item }) {
  const { ticket } = item;
  const { act, pending } = useAct();
  const { data: overview } = useOverview();
  const { data } = useTicket(ticket.id);
  const u = data ? latestUnderstanding(data.comments) : null;
  const c = overview?.control;
  const blocked = !c ? "Loading…" : c.mode === "paused" ? "Paused mode" : c.my_turn ? "The checkout is yours" : c.busy ? "An agent is already working" : null;

  const approveAndStart = async () => {
    if (await act(() => patch(`/api/tickets/${ticket.id}`, { status: "in_progress" }), "Approved"))
      await act(() => post(`/api/tickets/${ticket.id}/start`, { kind: "fix" }), "Fix started");
  };

  return (
    <CardShell
      item={item}
      actions={
        <>
          {blocked && <span className="text-xs text-muted-foreground">{blocked}</span>}
          <Button asChild size="sm" variant="ghost" className={QUIET}>
            <Link to={`/tickets/${ticket.id}`}>Correct it</Link>
          </Button>
          <Button size="sm" variant="secondary" disabled={pending} title="Approve without starting the fix yet" onClick={() => act(() => patch(`/api/tickets/${ticket.id}`, { status: "in_progress" }), "Approved")}>
            Approve only
          </Button>
          <Button size="sm" disabled={pending || !!blocked} title={blocked ?? undefined} onClick={approveAndStart} leftIcon={<ShieldCheck />}>Approve and start</Button>
        </>
      }>
      {u ? (
        <dl className="space-y-1">
          {u.where && (
            <div>
              <dt className="inline font-medium">Where: </dt>
              <dd className="inline">{u.where}</dd>
            </div>
          )}
          {u.expected && (
            <div>
              <dt className="inline font-medium">Expected: </dt>
              <dd className="inline">{u.expected}</dd>
            </div>
          )}
          {u.actual && (
            <div>
              <dt className="inline font-medium">Actual: </dt>
              <dd className="inline">{u.actual}</dd>
            </div>
          )}
        </dl>
      ) : (
        <p className="text-muted-foreground">{STATES.analyzed.hint}</p>
      )}
    </CardShell>
  );
}

/** Card with direct actions for tickets that have them; other states stay plain rows. */
export function hasActionCard(state: Item["state"]) {
  return state === "review" || state === "analyzed";
}

export function TicketActionCard({ item }: { item: Item }) {
  return item.state === "review" ? <ReviewCard item={item} /> : <AnalyzedCard item={item} />;
}
