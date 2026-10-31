import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"
import { Loader2 } from "lucide-react"
import { Slot } from "radix-ui"
import { COLORS, COLOR_NAMES, TINTABLE, type ColorName } from "./colors"

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 text-sm font-medium whitespace-nowrap transition-all outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4 select-none",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        outline:
          "border bg-background shadow-xs hover:bg-accent hover:text-accent-foreground dark:border-input dark:bg-input/30 dark:hover:bg-input/50",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost:
          "hover:bg-accent hover:text-accent-foreground dark:hover:bg-accent/50",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-4 py-2 has-[>svg]:px-3",
        xs: "h-6 gap-1 px-2 text-xs has-[>svg]:px-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-8 gap-1.5 px-3 has-[>svg]:px-2.5",
        lg: "h-10 px-6 has-[>svg]:px-4",
        icon: "size-9",
        "icon-xs": "size-6 [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-8",
        "icon-lg": "size-10",
      },
      /** Hue of the button; how it is painted still follows `variant`. Without it the button is the primary blue. */
      color: Object.fromEntries(COLOR_NAMES.map((c) => [c, ""])) as Record<ColorName, string>,
      radius: {
        none: "rounded-none",
        sm: "rounded-sm",
        md: "rounded-md",
        lg: "rounded-lg",
        xl: "rounded-xl",
        full: "rounded-full",
      },
    },
    compoundVariants: COLOR_NAMES.flatMap((color) => TINTABLE.map((variant) => ({ variant, color, className: COLORS[color][variant] }))),
    defaultVariants: {
      variant: "default",
      size: "default",
      radius: "md",
    },
  }
)

/**
 * A click handler that returns a promise (an API call) puts the button in a loading state until it
 * settles: spinner, disabled, aria-busy. `loading` forces it (e.g. submit buttons whose work runs in a form handler).
 */
function Button({
  className,
  variant = "default",
  size = "default",
  radius = "md",
  color,
  asChild = false,
  loading,
  leftIcon,
  rightIcon,
  onClick,
  disabled,
  children,
  ...props
}: Omit<React.ComponentProps<"button">, "color"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
    loading?: boolean
    /** Rendered before / after the children. Not applied with `asChild`, where the child element is the content. */
    leftIcon?: React.ReactNode
    rightIcon?: React.ReactNode
  }) {
  const Comp = asChild ? Slot.Root : "button"
  const [busy, setBusy] = React.useState(false)
  const mounted = React.useRef(true)
  // set on every mount: StrictMode (dev) mounts, unmounts and mounts again, and a ref set only by the
  // cleanup would stay false, leaving the button busy forever after its first click
  React.useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])
  const isLoading = !asChild && (loading ?? busy)

  const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
    const result = onClick?.(e) as unknown
    if (!asChild && result && typeof (result as Promise<unknown>).then === "function") {
      setBusy(true)
      void Promise.resolve(result).finally(() => mounted.current && setBusy(false))
    }
  }

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      data-radius={radius}
      data-color={color}
      aria-busy={isLoading || undefined}
      className={cn(buttonVariants({ variant, size, radius, color, className }), isLoading && "[&>svg:not([data-spinner])]:hidden")}
      disabled={disabled || isLoading}
      onClick={handleClick}
      {...props}
    >
      {asChild ? (
        children
      ) : (
        <>
          {isLoading && <Loader2 data-spinner className="animate-spin motion-reduce:animate-none" aria-hidden />}
          {leftIcon}
          {children}
          {rightIcon}
        </>
      )}
    </Comp>
  )
}

export { Button, buttonVariants }
