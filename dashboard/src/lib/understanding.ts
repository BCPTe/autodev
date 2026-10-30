import type { Comment } from "@/lib/api"

export interface Understanding {
  where?: string
  expected?: string
  actual?: string
  steps: string[]
  questions: string[]
  at: string | null
}

const HEADING = "What I understood"
const FIELDS = { Where: "where", Expected: "expected", Actual: "actual" } as const

/** Bullet lines under the heading that starts with `heading`, up to the next blank line. */
function section(lines: string[], heading: string): string[] {
  const start = lines.findIndex((l) => l.startsWith(heading))
  if (start < 0) return []
  const end = lines.findIndex((l, i) => i > start && !l.trim())
  return lines.slice(start + 1, end < 0 ? undefined : end)
}

/** "What I understood" and the open questions of the latest triage comment (written by pipeline.format_comment). */
export function latestUnderstanding(comments: Comment[]): Understanding | null {
  const triage = [...comments].reverse().find((c) => c.is_bot && c.text.startsWith("Triage:"))
  if (!triage) return null
  const lines = triage.text.split("\n")
  const u: Understanding = { steps: [], questions: section(lines, "Questions").map((l) => l.replace(/^- /, "")), at: triage.created_at }
  for (const line of section(lines, HEADING)) {
    const step = line.match(/^\s+\d+\.\s+(.*)$/)
    if (step) { u.steps.push(step[1]); continue }
    const field = line.match(/^- (Where|Expected|Actual): (.*)$/)
    if (field) u[FIELDS[field[1] as keyof typeof FIELDS]] = field[2]
  }
  return u.expected || u.actual || u.questions.length ? u : null
}
