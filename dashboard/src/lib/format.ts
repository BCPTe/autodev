export const money = (v: number) => `$${v.toFixed(2)}`

export function duration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds))
  const m = Math.floor(s / 60)
  return m >= 60 ? `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m` : `${m}:${String(s % 60).padStart(2, "0")}`
}

export function ago(input: number | string | null | undefined, now = Date.now()): string {
  if (input == null) return "—"
  const ms = typeof input === "number" ? input * 1000 : Date.parse(input)
  if (Number.isNaN(ms)) return "—"
  const s = Math.round((now - ms) / 1000)
  if (s < 45) return "ora"
  if (s < 3600) return `${Math.round(s / 60)} min fa`
  if (s < 86400) return `${Math.round(s / 3600)} h fa`
  return `${Math.round(s / 86400)} g fa`
}

export const shortModel = (m: string | null) =>
  m ? m.replace("claude-", "").replace(/-5-\d+$/, "").replace(/^\w/, (c) => c.toUpperCase()) : "—"
