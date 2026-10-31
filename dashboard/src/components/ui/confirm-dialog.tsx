import * as React from "react"
import { AlertDialog } from "radix-ui"
import { Button } from "@/components/ui/button"

type ConfirmDialogProps = {
  /** The element that opens the dialog; it is rendered as-is, so pass a Button. */
  trigger: React.ReactNode
  title: string
  description?: React.ReactNode
  confirmLabel?: string
  cancelLabel?: string
  /** Colour of the confirm button, e.g. "red" for destructive actions. */
  color?: React.ComponentProps<typeof Button>["color"]
  onConfirm: () => void
}

/** Asks before acting: the action runs only when the confirm button is pressed. */
export function ConfirmDialog({ trigger, title, description, confirmLabel = "Confirm", cancelLabel = "Cancel", color, onConfirm }: ConfirmDialogProps) {
  return (
    <AlertDialog.Root>
      <AlertDialog.Trigger asChild>{trigger}</AlertDialog.Trigger>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="fixed inset-0 z-50 bg-black/50 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0" />
        <AlertDialog.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-sm -translate-x-1/2 -translate-y-1/2 space-y-4 rounded-md border bg-background p-5 shadow-lg data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0">
          <div className="space-y-1.5">
            <AlertDialog.Title className="text-base font-semibold">{title}</AlertDialog.Title>
            {description && <AlertDialog.Description className="text-sm text-muted-foreground">{description}</AlertDialog.Description>}
          </div>
          <div className="flex justify-end gap-2">
            <AlertDialog.Cancel asChild>
              <Button size="sm" variant="outline">{cancelLabel}</Button>
            </AlertDialog.Cancel>
            <AlertDialog.Action asChild>
              <Button size="sm" color={color} onClick={onConfirm}>{confirmLabel}</Button>
            </AlertDialog.Action>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  )
}
