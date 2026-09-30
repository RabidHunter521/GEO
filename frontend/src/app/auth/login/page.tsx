"use client"

import { useEffect, useState } from "react"
import { signIn } from "next-auth/react"
import { AlertCircle, ArrowLeft, Eye, EyeOff, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { salutationForHour } from "@/lib/greeting"
import { BrandPanel } from "./BrandPanel"
import { COMPANY_LEGAL_NAME, COMPANY_REGISTRATION_NUMBER } from "@/lib/company"

export default function LoginPage() {
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  // Local time of day, resolved after mount: the server runs UTC and would
  // render the wrong salutation (same pattern as HomeGreeting). No name here —
  // the admin's display name is its username, which must not be shown to an
  // anonymous visitor.
  const [salutation, setSalutation] = useState("Welcome back")
  useEffect(() => setSalutation(salutationForHour(new Date().getHours())), [])

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    const data = new FormData(e.currentTarget)
    try {
      const result = await signIn("credentials", {
        username: data.get("username") as string,
        password: data.get("password") as string,
        callbackUrl: "/home",
        redirect: false,
      })
      if (result?.error) {
        setError("Invalid username or password")
        setLoading(false)
      } else if (result?.url) {
        // Navigating away — leave the button in its loading state.
        window.location.href = result.url
      } else {
        // No url and no error (e.g. the auth service was unreachable) — don't
        // leave the button stuck spinning with no feedback.
        setError("Something went wrong signing in. Please try again.")
        setLoading(false)
      }
    } catch {
      setError("Couldn't reach the server. Please try again.")
      setLoading(false)
    }
  }

  return (
    <div className="grid min-h-screen bg-background lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <main className="relative flex flex-col overflow-hidden bg-app-wash px-4 py-6 sm:px-8 short:py-4">
        <div
          aria-hidden
          className="animate-drift pointer-events-none absolute -right-32 -top-32 h-96 w-96 rounded-full bg-primary/10 blur-3xl"
        />

        <header className="relative flex justify-end">
          <a
            href="https://seenby.my"
            className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden />
            Back to seenby.my
          </a>
        </header>

        <div className="relative flex flex-1 items-center justify-center py-10 short:py-4">
          <Card className="reveal w-full max-w-md border-border/60 shadow-brand-lg">
            <CardHeader className="space-y-4 pb-4 short:space-y-3 tiny:pt-5">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/logo.png"
                alt="SeenBy"
                className="h-14 w-14 rounded-2xl shadow-brand short:h-11 short:w-11 tiny:h-9 tiny:w-9 tiny:rounded-xl"
              />
              <div className="space-y-1.5">
                <CardTitle className="font-display text-3xl tracking-tight short:text-2xl">
                  {salutation} <span aria-hidden>👋</span>
                </CardTitle>
                <CardDescription className="text-base short:text-sm">
                  Sign in to your SeenBy workspace.
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-4 tiny:space-y-3">
                <div className="space-y-2">
                  <Label htmlFor="username">Username</Label>
                  <Input
                    id="username"
                    name="username"
                    type="text"
                    autoComplete="username"
                    autoFocus
                    required
                    className="h-11 tiny:h-10"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="password">Password</Label>
                  <div className="relative">
                    <Input
                      id="password"
                      name="password"
                      type={showPassword ? "text" : "password"}
                      autoComplete="current-password"
                      required
                      className="h-11 pr-11 tiny:h-10"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((v) => !v)}
                      aria-label={showPassword ? "Hide password" : "Show password"}
                      aria-pressed={showPassword}
                      className="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-muted-foreground hover:text-foreground"
                    >
                      {showPassword ? (
                        <EyeOff className="h-4 w-4" aria-hidden />
                      ) : (
                        <Eye className="h-4 w-4" aria-hidden />
                      )}
                    </button>
                  </div>
                </div>
                {error && (
                  <div
                    role="alert"
                    className="flex items-start gap-2 rounded-lg border border-score-low/25 bg-score-low-bg px-3 py-2.5 text-sm text-destructive"
                  >
                    <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                    <span>{error}</span>
                  </div>
                )}
                <Button type="submit" className="h-11 w-full text-base tiny:h-10" disabled={loading}>
                  {loading ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden />
                      Signing in…
                    </>
                  ) : (
                    "Sign in"
                  )}
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>

        <footer className="relative flex flex-col items-center justify-between gap-1 text-xs text-muted-foreground sm:flex-row">
          <span>Admin access only</span>
          <span>
            © {new Date().getFullYear()} {COMPANY_LEGAL_NAME} ({COMPANY_REGISTRATION_NUMBER}) ·{" "}
            <a href="https://seenby.my" className="hover:text-foreground">
              seenby.my
            </a>
          </span>
        </footer>
      </main>

      <BrandPanel />
    </div>
  )
}
