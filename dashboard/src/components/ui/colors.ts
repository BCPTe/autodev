/**
 * Hues for `color`, one class string per `variant` that can be tinted. red, amber and green follow the theme
 * (destructive and the status lamps); the rest are Tailwind's palette. Written out in full because Tailwind
 * only generates classes it finds in the source.
 */
export const COLORS = {
  red: {
    default: "bg-destructive text-white hover:bg-destructive/90 focus-visible:ring-destructive/20 dark:bg-destructive/60 dark:focus-visible:ring-destructive/40",
    outline: "border-destructive/50 text-destructive hover:bg-destructive/10 hover:text-destructive",
    ghost: "text-destructive hover:bg-destructive/10 hover:text-destructive",
  },
  amber: {
    default: "bg-lamp-amber text-black hover:bg-lamp-amber/85 focus-visible:ring-lamp-amber/30",
    outline: "border-lamp-amber/60 text-lamp-amber hover:bg-lamp-amber/10 hover:text-lamp-amber",
    ghost: "text-lamp-amber hover:bg-lamp-amber/10 hover:text-lamp-amber",
  },
  green: {
    default: "bg-lamp-green text-black hover:bg-lamp-green/85 focus-visible:ring-lamp-green/30",
    outline: "border-lamp-green/60 text-lamp-green hover:bg-lamp-green/10 hover:text-lamp-green",
    ghost: "text-lamp-green hover:bg-lamp-green/10 hover:text-lamp-green",
  },
  orange: {
    default: "bg-orange-600 text-white hover:bg-orange-600/90 focus-visible:ring-orange-500/30 dark:bg-orange-500 dark:hover:bg-orange-500/90",
    outline: "border-orange-500/50 text-orange-600 hover:bg-orange-500/10 hover:text-orange-600 dark:text-orange-400 dark:hover:text-orange-400",
    ghost: "text-orange-600 hover:bg-orange-500/10 hover:text-orange-600 dark:text-orange-400 dark:hover:text-orange-400",
  },
  yellow: {
    default: "bg-yellow-400 text-black hover:bg-yellow-400/85 focus-visible:ring-yellow-400/30",
    outline: "border-yellow-500/50 text-yellow-600 hover:bg-yellow-500/10 hover:text-yellow-600 dark:text-yellow-400 dark:hover:text-yellow-400",
    ghost: "text-yellow-600 hover:bg-yellow-500/10 hover:text-yellow-600 dark:text-yellow-400 dark:hover:text-yellow-400",
  },
  lime: {
    default: "bg-lime-400 text-black hover:bg-lime-400/85 focus-visible:ring-lime-400/30",
    outline: "border-lime-500/50 text-lime-600 hover:bg-lime-500/10 hover:text-lime-600 dark:text-lime-400 dark:hover:text-lime-400",
    ghost: "text-lime-600 hover:bg-lime-500/10 hover:text-lime-600 dark:text-lime-400 dark:hover:text-lime-400",
  },
  emerald: {
    default: "bg-emerald-600 text-white hover:bg-emerald-600/90 focus-visible:ring-emerald-500/30 dark:bg-emerald-500 dark:hover:bg-emerald-500/90",
    outline: "border-emerald-500/50 text-emerald-600 hover:bg-emerald-500/10 hover:text-emerald-600 dark:text-emerald-400 dark:hover:text-emerald-400",
    ghost: "text-emerald-600 hover:bg-emerald-500/10 hover:text-emerald-600 dark:text-emerald-400 dark:hover:text-emerald-400",
  },
  teal: {
    default: "bg-teal-600 text-white hover:bg-teal-600/90 focus-visible:ring-teal-500/30 dark:bg-teal-500 dark:hover:bg-teal-500/90",
    outline: "border-teal-500/50 text-teal-600 hover:bg-teal-500/10 hover:text-teal-600 dark:text-teal-400 dark:hover:text-teal-400",
    ghost: "text-teal-600 hover:bg-teal-500/10 hover:text-teal-600 dark:text-teal-400 dark:hover:text-teal-400",
  },
  cyan: {
    default: "bg-cyan-600 text-white hover:bg-cyan-600/90 focus-visible:ring-cyan-500/30 dark:bg-cyan-500 dark:hover:bg-cyan-500/90",
    outline: "border-cyan-500/50 text-cyan-600 hover:bg-cyan-500/10 hover:text-cyan-600 dark:text-cyan-400 dark:hover:text-cyan-400",
    ghost: "text-cyan-600 hover:bg-cyan-500/10 hover:text-cyan-600 dark:text-cyan-400 dark:hover:text-cyan-400",
  },
  sky: {
    default: "bg-sky-600 text-white hover:bg-sky-600/90 focus-visible:ring-sky-500/30 dark:bg-sky-500 dark:hover:bg-sky-500/90",
    outline: "border-sky-500/50 text-sky-600 hover:bg-sky-500/10 hover:text-sky-600 dark:text-sky-400 dark:hover:text-sky-400",
    ghost: "text-sky-600 hover:bg-sky-500/10 hover:text-sky-600 dark:text-sky-400 dark:hover:text-sky-400",
  },
  blue: {
    default: "bg-blue-600 text-white hover:bg-blue-600/90 focus-visible:ring-blue-500/30 dark:bg-blue-500 dark:hover:bg-blue-500/90",
    outline: "border-blue-500/50 text-blue-600 hover:bg-blue-500/10 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-400",
    ghost: "text-blue-600 hover:bg-blue-500/10 hover:text-blue-600 dark:text-blue-400 dark:hover:text-blue-400",
  },
  indigo: {
    default: "bg-indigo-600 text-white hover:bg-indigo-600/90 focus-visible:ring-indigo-500/30 dark:bg-indigo-500 dark:hover:bg-indigo-500/90",
    outline: "border-indigo-500/50 text-indigo-600 hover:bg-indigo-500/10 hover:text-indigo-600 dark:text-indigo-400 dark:hover:text-indigo-400",
    ghost: "text-indigo-600 hover:bg-indigo-500/10 hover:text-indigo-600 dark:text-indigo-400 dark:hover:text-indigo-400",
  },
  violet: {
    default: "bg-violet-600 text-white hover:bg-violet-600/90 focus-visible:ring-violet-500/30 dark:bg-violet-500 dark:hover:bg-violet-500/90",
    outline: "border-violet-500/50 text-violet-600 hover:bg-violet-500/10 hover:text-violet-600 dark:text-violet-400 dark:hover:text-violet-400",
    ghost: "text-violet-600 hover:bg-violet-500/10 hover:text-violet-600 dark:text-violet-400 dark:hover:text-violet-400",
  },
  purple: {
    default: "bg-purple-600 text-white hover:bg-purple-600/90 focus-visible:ring-purple-500/30 dark:bg-purple-500 dark:hover:bg-purple-500/90",
    outline: "border-purple-500/50 text-purple-600 hover:bg-purple-500/10 hover:text-purple-600 dark:text-purple-400 dark:hover:text-purple-400",
    ghost: "text-purple-600 hover:bg-purple-500/10 hover:text-purple-600 dark:text-purple-400 dark:hover:text-purple-400",
  },
  fuchsia: {
    default: "bg-fuchsia-600 text-white hover:bg-fuchsia-600/90 focus-visible:ring-fuchsia-500/30 dark:bg-fuchsia-500 dark:hover:bg-fuchsia-500/90",
    outline: "border-fuchsia-500/50 text-fuchsia-600 hover:bg-fuchsia-500/10 hover:text-fuchsia-600 dark:text-fuchsia-400 dark:hover:text-fuchsia-400",
    ghost: "text-fuchsia-600 hover:bg-fuchsia-500/10 hover:text-fuchsia-600 dark:text-fuchsia-400 dark:hover:text-fuchsia-400",
  },
  pink: {
    default: "bg-pink-600 text-white hover:bg-pink-600/90 focus-visible:ring-pink-500/30 dark:bg-pink-500 dark:hover:bg-pink-500/90",
    outline: "border-pink-500/50 text-pink-600 hover:bg-pink-500/10 hover:text-pink-600 dark:text-pink-400 dark:hover:text-pink-400",
    ghost: "text-pink-600 hover:bg-pink-500/10 hover:text-pink-600 dark:text-pink-400 dark:hover:text-pink-400",
  },
  rose: {
    default: "bg-rose-600 text-white hover:bg-rose-600/90 focus-visible:ring-rose-500/30 dark:bg-rose-500 dark:hover:bg-rose-500/90",
    outline: "border-rose-500/50 text-rose-600 hover:bg-rose-500/10 hover:text-rose-600 dark:text-rose-400 dark:hover:text-rose-400",
    ghost: "text-rose-600 hover:bg-rose-500/10 hover:text-rose-600 dark:text-rose-400 dark:hover:text-rose-400",
  },
  slate: {
    default: "bg-slate-600 text-white hover:bg-slate-600/90 focus-visible:ring-slate-500/30 dark:bg-slate-500 dark:hover:bg-slate-500/90",
    outline: "border-slate-500/50 text-slate-600 hover:bg-slate-500/10 hover:text-slate-600 dark:text-slate-400 dark:hover:text-slate-400",
    ghost: "text-slate-600 hover:bg-slate-500/10 hover:text-slate-600 dark:text-slate-400 dark:hover:text-slate-400",
  },
  gray: {
    default: "bg-gray-600 text-white hover:bg-gray-600/90 focus-visible:ring-gray-500/30 dark:bg-gray-500 dark:hover:bg-gray-500/90",
    outline: "border-gray-500/50 text-gray-600 hover:bg-gray-500/10 hover:text-gray-600 dark:text-gray-400 dark:hover:text-gray-400",
    ghost: "text-gray-600 hover:bg-gray-500/10 hover:text-gray-600 dark:text-gray-400 dark:hover:text-gray-400",
  },
  zinc: {
    default: "bg-zinc-600 text-white hover:bg-zinc-600/90 focus-visible:ring-zinc-500/30 dark:bg-zinc-500 dark:hover:bg-zinc-500/90",
    outline: "border-zinc-500/50 text-zinc-600 hover:bg-zinc-500/10 hover:text-zinc-600 dark:text-zinc-400 dark:hover:text-zinc-400",
    ghost: "text-zinc-600 hover:bg-zinc-500/10 hover:text-zinc-600 dark:text-zinc-400 dark:hover:text-zinc-400",
  },
  neutral: {
    default: "bg-neutral-600 text-white hover:bg-neutral-600/90 focus-visible:ring-neutral-500/30 dark:bg-neutral-500 dark:hover:bg-neutral-500/90",
    outline: "border-neutral-500/50 text-neutral-600 hover:bg-neutral-500/10 hover:text-neutral-600 dark:text-neutral-400 dark:hover:text-neutral-400",
    ghost: "text-neutral-600 hover:bg-neutral-500/10 hover:text-neutral-600 dark:text-neutral-400 dark:hover:text-neutral-400",
  },
  stone: {
    default: "bg-stone-600 text-white hover:bg-stone-600/90 focus-visible:ring-stone-500/30 dark:bg-stone-500 dark:hover:bg-stone-500/90",
    outline: "border-stone-500/50 text-stone-600 hover:bg-stone-500/10 hover:text-stone-600 dark:text-stone-400 dark:hover:text-stone-400",
    ghost: "text-stone-600 hover:bg-stone-500/10 hover:text-stone-600 dark:text-stone-400 dark:hover:text-stone-400",
  },
} as const

export type ColorName = keyof typeof COLORS
export const TINTABLE = ["default", "outline", "ghost"] as const
export const COLOR_NAMES = Object.keys(COLORS) as ColorName[]
