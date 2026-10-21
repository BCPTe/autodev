import { useEffect, useRef } from "react"
import { useRunStream } from "@/hooks/useRunStream"
import { cn } from "@/lib/utils"

const offset = (t: number, t0: number) => {
  const s = Math.max(0, Math.round(t - t0))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`
}

/** Live action stream of one run (what the agent reads, searches, edits and runs). */
export function RunFeed({ runId, className }: { runId: number; className?: string }) {
  const { events, ended } = useRunStream(runId)
  const box = useRef<HTMLDivElement>(null)
  const stick = useRef(true)

  useEffect(() => {
    const el = box.current
    if (el && stick.current) el.scrollTop = el.scrollHeight
  }, [events.length])

  const t0 = events[0]?.ts ?? 0
  const lines = events.filter((e) => e.type !== "result")
  const result = events.find((e) => e.type === "result")

  return (
    <div className={cn("flex min-h-0 flex-col", className)}>
      <div
        ref={box}
        onScroll={(e) => {
          const el = e.currentTarget
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24
        }}
        role="log"
        aria-live="off"
        className="min-h-24 flex-1 overflow-y-auto rounded-sm bg-muted/60 p-3 font-mono text-[12.5px] leading-relaxed"
      >
        {lines.length === 0 && <p className="text-muted-foreground">Waiting for the first events…</p>}
        {lines.map((e) => (
          <div
            key={e.id}
            className={cn(
              "flex gap-3",
              e.type === "error" && "text-destructive",
              (e.type === "cancelled" || e.type === "paused" || e.type === "permission" || e.type === "checkpoint") && "text-lamp-amber",
              e.type === "user" && "my-1 rounded-sm border-l-2 border-primary bg-accent/50 py-1 pl-2 font-sans text-[13px]",
              e.type === "agent" && "my-1 font-sans text-[13px] italic",
              e.type === "decision" && "text-muted-foreground",
            )}
          >
            <span className="w-10 shrink-0 text-right tabular-nums text-muted-foreground">{offset(e.ts, t0)}</span>
            <span className="min-w-0 whitespace-pre-wrap break-words">
              {e.type === "user" && <strong className="mr-1 not-italic">You:</strong>}
              {e.type === "permission" && "Asks for permission: "}
              {e.type === "checkpoint" && "Waiting for your approval: "}
              {e.text.replace(/^\[\d+:\d+\]\s*/, "")}
            </span>
          </div>
        ))}
        {!ended && lines.length > 0 && <div className="pl-[52px] text-muted-foreground">▍</div>}
      </div>
      {result && (
        <div className="mt-3">
          <h4 className="mb-1 font-display text-sm font-semibold">Outcome</h4>
          <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-sm border bg-card p-3 font-sans text-[13px] leading-relaxed">{result.text}</pre>
        </div>
      )}
    </div>
  )
}
