import { useEffect, useRef } from "react"
import { useOverview } from "@/hooks/queries"

const KEY = "autodev:browser-notifications"

export const browserNotificationsOn = () => {
  try {
    return localStorage.getItem(KEY) === "1" && typeof Notification !== "undefined" && Notification.permission === "granted"
  } catch {
    return false
  }
}

export async function setBrowserNotifications(on: boolean): Promise<boolean> {
  if (on && typeof Notification !== "undefined" && Notification.permission !== "granted") {
    if ((await Notification.requestPermission()) !== "granted") return false
  }
  try {
    localStorage.setItem(KEY, on ? "1" : "0")
  } catch {
    /* ignore */
  }
  return on
}

/** Puts the number of things waiting for you in the tab title and, if enabled, notifies about new ones. */
export function useAttention() {
  const { data } = useOverview()
  const seen = useRef<Set<string> | null>(null)

  useEffect(() => {
    if (!data) return
    const items = [
      ...data.approvals.map((a) => ({ key: `a${a.id}`, text: a.title })),
      ...data.inbox.filter((i) => i.state !== "needs_info").map((i) => ({ key: `t${i.ticket.id}:${i.state}`, text: i.ticket.title })),
      ...data.recent_problems.map((r) => ({ key: `r${r.id}`, text: `${r.ticket_title}: ${r.error ?? "did not succeed"}` })),
    ]
    document.title = data.approvals.length ? `(${data.approvals.length}) autodev` : "autodev"
    if (seen.current && browserNotificationsOn() && document.hidden) {
      for (const it of items) if (!seen.current.has(it.key)) new Notification("autodev", { body: it.text })
    }
    seen.current = new Set(items.map((i) => i.key))
  }, [data])
}
