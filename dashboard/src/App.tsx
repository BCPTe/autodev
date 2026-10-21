import { useEffect } from "react"
import { BrowserRouter, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from "@tanstack/react-query"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { Shell } from "@/components/Shell"
import { api, UNAUTHORIZED_EVENT } from "@/lib/api"
import { ThemeProvider } from "@/lib/theme"
import { Costs } from "@/pages/Costs"
import { Login } from "@/pages/Login"
import { Now } from "@/pages/Now"
import { Prs } from "@/pages/Prs"
import { Repo } from "@/pages/Repo"
import { RunDetail } from "@/pages/RunDetail"
import { Runs } from "@/pages/Runs"
import { Settings } from "@/pages/Settings"
import { Tickets } from "@/pages/Tickets"

const client = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: true, staleTime: 2000 } } })

function Gate() {
  const qc = useQueryClient()
  const { data, isLoading, isError } = useQuery({
    queryKey: ["auth"],
    queryFn: () => api<{ setup_required: boolean; authenticated: boolean }>("/api/auth/state"),
  })

  useEffect(() => {
    const onExpired = () => qc.invalidateQueries({ queryKey: ["auth"] })
    window.addEventListener(UNAUTHORIZED_EVENT, onExpired)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onExpired)
  }, [qc])

  if (isLoading) return null
  if (isError || !data) {
    return (
      <main className="grid min-h-screen place-items-center px-4 text-center">
        <p className="max-w-sm text-muted-foreground">Il server non risponde. Avvia la dashboard con <code className="font-mono">uv run autodev serve</code> e ricarica la pagina.</p>
      </main>
    )
  }
  if (!data.authenticated) return <Login setupRequired={data.setup_required} onDone={() => qc.invalidateQueries({ queryKey: ["auth"] })} />

  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<Now />} />
          <Route path="tickets" element={<Tickets />} />
          <Route path="runs" element={<Runs />} />
          <Route path="runs/:id" element={<RunDetail />} />
          <Route path="repo" element={<Repo />} />
          <Route path="prs" element={<Prs />} />
          <Route path="costs" element={<Costs />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={client}>
        <TooltipProvider>
          <Gate />
          <Toaster />
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
