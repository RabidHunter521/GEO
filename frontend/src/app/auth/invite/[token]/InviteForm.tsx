"use client"

import { useActionState, useState } from "react"
import { AlertCircle, Eye, EyeOff, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { acceptInviteAction } from "./actions"

// Mirrors USER_PASSWORD_MIN_LENGTH in backend app/core/constants.py (the API
// enforces it; this only gives earlier feedback).
const PASSWORD_MIN_LENGTH = 12

export function InviteForm({ token, qrSvg, secret }: { token: string; qrSvg: string; secret: string }) {
  const [state, formAction, pending] = useActionState(acceptInviteAction.bind(null, token), { error: null })
  const [show, setShow] = useState(false)

  return (
    <form action={formAction} className="space-y-6">
      <section className="space-y-3">
        <h2 className="text-sm font-semibold">1. Connect your authenticator app</h2>
        <p className="text-sm text-muted-foreground">
          Scan this QR code with Google Authenticator, 1Password, Authy or similar.
        </p>
        <div className="flex flex-col items-center gap-3 sm:flex-row sm:items-start">
          <div
            className="h-40 w-40 shrink-0 rounded-lg border bg-white p-2"
            role="img"
            aria-label="QR code for your authenticator app"
            // The SVG is generated on our server from our own otpauth URI.
            dangerouslySetInnerHTML={{ __html: qrSvg }}
          />
          <div className="min-w-0 text-xs text-muted-foreground">
            <p>Can&apos;t scan? Enter this key manually:</p>
            <code className="mt-1 block break-all rounded bg-muted px-2 py-1.5 font-mono text-sm text-foreground">
              {secret.replace(/(.{4})/g, "$1 ").trim()}
            </code>
          </div>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold">2. Choose a password</h2>
        <div className="space-y-2">
          <Label htmlFor="password">Password</Label>
          <div className="relative">
            <Input
              id="password"
              name="password"
              type={show ? "text" : "password"}
              autoComplete="new-password"
              minLength={PASSWORD_MIN_LENGTH}
              required
              className="h-11 pr-11"
              aria-describedby="password-hint"
            />
            <button
              type="button"
              onClick={() => setShow((v) => !v)}
              aria-label={show ? "Hide password" : "Show password"}
              aria-pressed={show}
              className="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-muted-foreground hover:text-foreground"
            >
              {show ? <EyeOff className="h-4 w-4" aria-hidden /> : <Eye className="h-4 w-4" aria-hidden />}
            </button>
          </div>
          <p id="password-hint" className="text-xs text-muted-foreground">
            At least {PASSWORD_MIN_LENGTH} characters. A short sentence works well.
          </p>
        </div>
        <div className="space-y-2">
          <Label htmlFor="confirm">Confirm password</Label>
          <Input
            id="confirm"
            name="confirm"
            type={show ? "text" : "password"}
            autoComplete="new-password"
            minLength={PASSWORD_MIN_LENGTH}
            required
            className="h-11"
          />
        </div>
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-semibold">3. Confirm with a code</h2>
        <Label htmlFor="code">6-digit code from the app</Label>
        <Input
          id="code"
          name="code"
          inputMode="numeric"
          autoComplete="one-time-code"
          pattern="[0-9 ]{6,7}"
          maxLength={7}
          required
          placeholder="123456"
          className="h-11 tracking-[0.3em]"
        />
      </section>

      {state.error && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-lg border border-score-low/25 bg-score-low-bg px-3 py-2.5 text-sm text-destructive"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <span>{state.error}</span>
        </div>
      )}

      <Button type="submit" className="h-11 w-full text-base" disabled={pending}>
        {pending ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden />
            Setting up…
          </>
        ) : (
          "Finish setup"
        )}
      </Button>
    </form>
  )
}
