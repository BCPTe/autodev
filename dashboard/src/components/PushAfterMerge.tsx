import { useEffect, useState } from "react"
import { Dialog } from "radix-ui"
import { X } from "lucide-react"
import { PushPanel } from "@/components/PushPanel"
import { Button } from "@/components/ui/button"

export const MERGED_EVENT = "autodev:merged"

/** Opens right after a branch is merged locally and offers the push. Mounted once, in the shell, so it outlives the ticket's buttons. */
export function PushAfterMerge() {
  const [open, setOpen] = useState(false)
  useEffect(() => {
    const show = () => setOpen(true)
    window.addEventListener(MERGED_EVENT, show)
    return () => window.removeEventListener(MERGED_EVENT, show)
  }, [])
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 data-[state=open]:animate-in data-[state=open]:fade-in-0" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(40rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 space-y-4 rounded-xl border bg-background p-6 shadow-xl">
          <div className="flex items-start justify-between gap-4">
            <div>
              <Dialog.Title className="text-lg font-semibold">Merged; the ticket is closed</Dialog.Title>
              <Dialog.Description className="mt-0.5 text-[13px] text-muted-foreground">The change is on your computer only. Pushing it to origin is a separate step, so you decide when.</Dialog.Description>
            </div>
            <Dialog.Close asChild><Button size="icon" variant="ghost" aria-label="Close"><X /></Button></Dialog.Close>
          </div>
          <PushPanel onDone={() => setOpen(false)} />
          <div className="flex justify-end"><Button variant="outline" onClick={() => setOpen(false)}>Not now</Button></div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
