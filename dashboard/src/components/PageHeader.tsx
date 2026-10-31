import type { ReactNode } from "react"

export function PageHeader({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <header className="mb-8">
      <h1 className="text-4xl font-semibold leading-none tracking-[-0.01em] select-none">{title}</h1>
      {children && <div className="mt-2 max-w-[68ch] text-[15px] text-muted-foreground">{children}</div>}
      <div aria-hidden className="relative mt-5 h-px bg-border">
        <span className="absolute left-0 top-1/2 h-0.75 w-14 -translate-y-1/2 rounded-full bg-primary" />
      </div>
    </header>
  )
}
