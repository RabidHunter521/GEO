"use client"

import { useState } from "react"
import { signIn } from "next-auth/react"
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

export default function LoginPage() {
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

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
    <div className="flex min-h-screen items-center justify-center bg-app-wash bg-background p-4">
      <Card className="w-full max-w-sm shadow-brand">
        <CardHeader className="space-y-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/logo.png"
            alt="SeenBy"
            className="h-11 w-11 rounded-xl shadow-brand"
          />
          <div className="space-y-1">
            <CardTitle className="text-2xl">SeenBy</CardTitle>
            <CardDescription>Admin access only</CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                name="username"
                type="text"
                autoComplete="username"
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
              />
            </div>
            {error && (
              <p className="text-sm text-destructive">{error}</p>
            )}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
