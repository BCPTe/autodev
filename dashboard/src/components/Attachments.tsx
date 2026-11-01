import { ExternalLink, FileText, Paperclip } from "lucide-react"
import { useAttachments } from "@/hooks/queries"
import { scoped, type AttachmentInfo } from "@/lib/api"

const fileUrl = (ticketId: string, a: AttachmentInfo) => scoped(`/api/tickets/${encodeURIComponent(ticketId)}/attachments/${encodeURIComponent(a.saved ?? "")}`)

/** Files attached to the ticket: pictures as thumbnails, everything else as a row. They are served by autodev, not by Notion. */
export function Attachments({ ticketId }: { ticketId: string }) {
  const { data } = useAttachments(ticketId)
  const files = data?.attachments ?? []
  if (!files.length) return null
  const pictures = files.filter((a) => !a.external && a.type.startsWith("image/") && a.inline)
  const others = files.filter((a) => !pictures.includes(a))
  return (
    <section aria-labelledby="attachments">
      <h2 id="attachments" className="mb-2 flex items-center gap-2 text-lg font-semibold">
        <Paperclip className="size-4 text-muted-foreground" aria-hidden /> Attachments
        <span className="text-sm font-normal text-muted-foreground">{files.length}</span>
      </h2>
      {pictures.length > 0 && (
        <ul className="mb-3 flex flex-wrap gap-3">
          {pictures.map((a) => (
            <li key={a.saved}>
              <a href={fileUrl(ticketId, a)} target="_blank" rel="noreferrer" title={a.name} className="block overflow-hidden border bg-card transition-colors hover:border-primary/60">
                <img src={fileUrl(ticketId, a)} alt={a.name} loading="lazy" className="h-32 w-auto max-w-64 object-cover" />
              </a>
            </li>
          ))}
        </ul>
      )}
      {others.length > 0 && (
        <ul className="max-w-[72ch] divide-y border-y text-[14px]">
          {others.map((a) => (
            <li key={a.saved ?? a.url}>
              <a href={a.external ? (a.url ?? "#") : fileUrl(ticketId, a)} target="_blank" rel="noreferrer" className="flex items-center gap-2 py-2 hover:text-primary">
                {a.external ? <ExternalLink className="size-4 shrink-0 text-muted-foreground" aria-hidden /> : <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden />}
                <span className="min-w-0 flex-1 truncate">{a.name}</span>
                <span className="shrink-0 text-xs text-muted-foreground">{a.external ? "link" : a.inline ? "open" : "download"}</span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
