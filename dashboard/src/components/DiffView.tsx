import { useState } from "react"
import { ChevronRight } from "lucide-react"
import { Skeleton } from "@/components/ui/skeleton"
import { useDiff } from "@/hooks/queries"
import { cn } from "@/lib/utils"

function Patch({ text }: { text: string }) {
  const lines = text.split("\n").filter((l) => !/^(diff --git|index |--- |\+\+\+ |new file|deleted file)/.test(l))
  return (
    <pre className="overflow-x-auto bg-card py-2 font-mono text-[12px] leading-[1.55]">
      {lines.map((l, i) => (
        <div
          key={i}
          className={cn(
            "whitespace-pre px-3",
            l.startsWith("+") && "bg-lamp-green/15",
            l.startsWith("-") && "bg-lamp-red/15",
            l.startsWith("@@") && "text-muted-foreground",
          )}
        >
          {l || " "}
        </div>
      ))}
    </pre>
  )
}

/** File-by-file changes of an agent branch (or the uncommitted ones when `branch` is null). */
export function DiffView({ branch }: { branch: string | null }) {
  const { data, isLoading, error } = useDiff(branch, true)
  const [open, setOpen] = useState<Set<string>>(new Set())
  if (isLoading) return <Skeleton className="h-24 w-full" />
  if (error) return <p className="text-destructive">{(error as Error).message}</p>
  if (!data || data.files.length === 0) return <p className="text-muted-foreground">No differences.</p>
  const toggle = (p: string) => setOpen((s) => { const n = new Set(s); if (n.has(p)) n.delete(p); else n.add(p); return n })
  const add = data.files.reduce((n, f) => n + (f.additions ?? 0), 0)
  const del = data.files.reduce((n, f) => n + (f.deletions ?? 0), 0)

  return (
    <div className="overflow-hidden rounded-sm border">
      <p className="border-b bg-muted/50 px-3 py-1.5 text-[13px]">
        {data.files.length} file · <span className="text-lamp-green">+{add}</span> <span className="text-lamp-red">−{del}</span>
      </p>
      <ul className="divide-y">
        {data.files.map((f) => (
          <li key={f.path}>
            <button className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-muted/50" aria-expanded={open.has(f.path)} onClick={() => toggle(f.path)}>
              <ChevronRight className={cn("size-3.5 shrink-0 transition-transform", open.has(f.path) && "rotate-90")} aria-hidden />
              <span className="min-w-0 flex-1 truncate font-mono text-[12.5px]">{f.path}</span>
              <span className="whitespace-nowrap text-xs tabular-nums">
                {f.additions == null ? "binary" : <><span className="text-lamp-green">+{f.additions}</span> <span className="text-lamp-red">−{f.deletions}</span></>}
              </span>
            </button>
            {open.has(f.path) && (f.truncated ? <p className="px-3 py-2 text-[13px] text-muted-foreground">Diff too large to show here: open it with git.</p> : f.patch ? <Patch text={f.patch} /> : <p className="px-3 py-2 text-[13px] text-muted-foreground">Nothing to show.</p>)}
          </li>
        ))}
      </ul>
    </div>
  )
}
