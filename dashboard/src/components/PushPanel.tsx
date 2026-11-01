import { ArrowUpFromLine } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { usePushPlan } from "@/hooks/queries"
import { useAct } from "@/hooks/useAct"
import { post } from "@/lib/api"

/**
 * Pushing the base branch to origin, with the list of commits that would go out. Nothing is hidden: commits that are
 * not autodev's are marked, because git sends every commit that came before the one being pushed.
 */
export function PushPanel({ onDone, quiet = false }: { onDone?: () => void; quiet?: boolean }) {
  const { data: plan, isLoading } = usePushPlan()
  const { act, pending } = useAct()
  if (isLoading) return <Skeleton className="h-16 w-full" />
  if (!plan) return null
  if (!plan.can_push && !plan.reason) return null
  // when there is nothing to send, say so only where the person came to push; elsewhere stay out of the way
  if (!plan.can_push && quiet) return null
  const push = async () => {
    const ok = await act(() => post("/api/repo/push", { confirm: true }), (r) => `Pushed ${(r as { pushed: number }).pushed} ${(r as { pushed: number }).pushed === 1 ? "commit" : "commits"} to origin/${plan.base}`)
    if (ok) onDone?.()
  }
  return (
    <section aria-label="Push to origin" className="rounded-lg border bg-card p-4">
      <h2 className="mb-1 text-[15px] font-medium">{plan.can_push ? `Not on origin yet: ${plan.commits.length} ${plan.commits.length === 1 ? "commit" : "commits"} on ${plan.base}` : "Nothing to push"}</h2>
      {plan.can_push ? (
        <>
          <ul className="mb-3 divide-y border-y text-[13px]">
            {plan.commits.map((c) => (
              <li key={c.sha} className="flex items-center gap-2 py-1.5">
                <span className="font-mono text-xs text-muted-foreground">{c.sha}</span>
                <span className="min-w-0 flex-1 truncate">{c.subject}</span>
                <span className={c.autodev ? "text-xs text-muted-foreground" : "rounded-sm bg-lamp-amber/15 px-1.5 py-0.5 text-xs font-medium text-lamp-amber"}>{c.autodev ? "autodev" : "yours"}</span>
              </li>
            ))}
          </ul>
          {!!plan.own_count && <p className="mb-3 text-[13px] text-muted-foreground">{plan.own_count === 1 ? "One commit of yours comes first" : `${plan.own_count} commits of yours come first`}, so it goes out too: git always sends the commits before the one being pushed.</p>}
          <div className="flex items-center gap-3">
            <Button loading={pending} onClick={push} leftIcon={<ArrowUpFromLine />}>Push to origin/{plan.base}</Button>
            <span className="text-[13px] text-muted-foreground">Never forced: git refuses anything but a plain advance.</span>
          </div>
        </>
      ) : <p className="text-[13px] text-muted-foreground">{plan.reason}</p>}
    </section>
  )
}
