import { useState, type FormEvent } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ApiError, post } from "@/lib/api"

function Track() {
  return (
    <div aria-hidden className="relative mb-8 flex items-center justify-between">
      <div className="absolute inset-x-1 top-1/2 h-px bg-rail" />
      {[0, 1, 2, 3, 4].map((i) => (
        <span key={i} className={`relative size-2.5 rounded-full ${i === 2 ? "bg-primary" : "bg-rail"}`} />
      ))}
    </div>
  )
}

export function Login({ setupRequired, onDone }: { setupRequired: boolean; onDone: () => void }) {
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [code, setCode] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (setupRequired && password !== confirm) {
      setError("The two passwords do not match.")
      return
    }
    setBusy(true)
    try {
      await post(setupRequired ? "/api/auth/setup" : "/api/auth/login", setupRequired ? { password, code: code.trim() } : { password })
      onDone()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Server unreachable. Check that `autodev` is running.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="grid min-h-screen place-items-center px-4">
      <form onSubmit={submit} className="w-full max-w-sm">
        <Track />
        <h1 className="text-3xl font-semibold">{setupRequired ? "First setup" : "Sign in to autodev"}</h1>
        <p className="mb-6 mt-1 text-muted-foreground">
          {setupRequired
            ? "Choose the dashboard password. The setup code is printed in the terminal where you started `autodev`."
            : "The dashboard is local to this computer."}
        </p>

        <div className="space-y-4">
          {setupRequired && (
            <div className="space-y-1.5">
              <Label htmlFor="code">Setup code</Label>
              <Input id="code" value={code} onChange={(e) => setCode(e.target.value)} autoComplete="off" autoFocus required className="font-mono" />
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="password">Password{setupRequired && " (at least 10 characters)"}</Label>
            <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={setupRequired ? "new-password" : "current-password"} autoFocus={!setupRequired} required />
          </div>
          {setupRequired && (
            <div className="space-y-1.5">
              <Label htmlFor="confirm">Repeat the password</Label>
              <Input id="confirm" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" required />
            </div>
          )}
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          <Button type="submit" className="w-full" loading={busy}>
            {busy ? "Please wait…" : setupRequired ? "Create password and sign in" : "Sign in"}
          </Button>
        </div>
      </form>
    </main>
  )
}
