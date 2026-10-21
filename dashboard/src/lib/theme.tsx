import { createContext, useContext, useEffect, useState, type ReactNode } from "react"

type Theme = "light" | "dark" | "system"
const KEY = "autodev-theme"
const Ctx = createContext<{ theme: Theme; dark: boolean; setTheme: (t: Theme) => void }>({ theme: "system", dark: false, setTheme: () => {} })

function stored(): Theme {
  try {
    const v = localStorage.getItem(KEY)
    if (v === "light" || v === "dark" || v === "system") return v
  } catch {
    /* storage can be blocked: fall back to the system theme */
  }
  return "system"
}

const prefersDark = () => window.matchMedia("(prefers-color-scheme: dark)").matches
const isDark = (theme: Theme) => theme === "dark" || (theme === "system" && prefersDark())

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(stored)
  const [dark, setDark] = useState(() => isDark(stored()))
  useEffect(() => {
    const update = () => setDark(isDark(theme))
    update()
    const mq = window.matchMedia("(prefers-color-scheme: dark)")
    mq.addEventListener("change", update)
    return () => mq.removeEventListener("change", update)
  }, [theme])
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark)
  }, [dark])
  const setTheme = (t: Theme) => {
    try {
      localStorage.setItem(KEY, t)
    } catch {
      /* not persisted */
    }
    setThemeState(t)
  }
  return <Ctx.Provider value={{ theme, dark, setTheme }}>{children}</Ctx.Provider>
}

export const useTheme = () => useContext(Ctx)
