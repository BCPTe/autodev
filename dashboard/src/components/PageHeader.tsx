import type { ReactNode } from "react"

export function PageHeader({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <h1 className="text-3xl font-semibold">{title}</h1>
      {children && <div className="text-sm text-muted-foreground">{children}</div>}
    </div>
  )
}
