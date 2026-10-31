import { cn } from "@/lib/utils"
import type { Lamp as LampKind } from "@/lib/status"

const COLOR: Record<LampKind, string> = {
  idle: "bg-lamp-idle",
  amber: "bg-lamp-amber",
  green: "bg-lamp-green",
  red: "bg-lamp-red",
  violet: "bg-lamp-violet",
  blue: "bg-lamp-blue",
}

export function Lamp({ kind, live = false, className }: { kind: LampKind; live?: boolean; className?: string }) {
  return <span aria-hidden className={cn("inline-block size-2.5 shrink-0 rounded-full", COLOR[kind], live && "animate-pulse motion-reduce:animate-none", className)} />
}
