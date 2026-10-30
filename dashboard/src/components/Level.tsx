import { cn } from "@/lib/utils";

const LEVELS = ["low", "medium", "high"] as const;
const LEVEL_COLOR = ["bg-lamp-green", "bg-lamp-amber", "bg-lamp-red"];

/** Low/Medium/High as three rising bars, filled up to the level in its colour. */
export function Level({ value }: { value: string | null }) {
  const i = LEVELS.indexOf((value ?? "").toLowerCase() as (typeof LEVELS)[number]);
  if (i < 0) return value;
  return (
    <>
      <span aria-hidden className="flex items-end gap-0.5">
        {LEVELS.map((_, j) => (
          <span key={j} className={cn("w-1.5 rounded-[1px]", ["h-1.5", "h-2.5", "h-3.5"][j], j <= i ? LEVEL_COLOR[i] : "bg-rail")} />
        ))}
      </span>
      <span className="font-medium">{value}</span>
    </>
  );
}
