import type { DashboardItem } from "@/lib/api"

/** Card with direct actions for tickets that have them; other states stay plain rows. */
export function hasActionCard(state: DashboardItem["state"]) {
  return state === "review" || state === "analyzed"
}
