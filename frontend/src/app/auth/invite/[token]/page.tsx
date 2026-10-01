// Public page behind a one-time invite / reset link (48 h). The invitee sets
// a password and connects an authenticator app in one step; 2FA is mandatory.
import QRCode from "qrcode"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { getInviteLink } from "@/lib/auth-api"
import { COMPANY_IDENTITY_LINE } from "@/lib/company"
import { InviteForm } from "./InviteForm"

export default async function InvitePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params
  const info = await getInviteLink(token)

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-app-wash bg-background px-4 py-10">
      <Card className="w-full max-w-lg shadow-brand-lg">
        <CardHeader className="space-y-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.png" alt="SeenBy" className="h-11 w-11 rounded-xl shadow-brand" />
          {info ? (
            <div className="space-y-1">
              <CardTitle className="font-display text-2xl tracking-tight">
                {info.is_reset ? "Reset your sign-in" : `Welcome, ${info.name}`}
              </CardTitle>
              <CardDescription className="text-base">
                Set up the SeenBy admin account for <strong className="text-foreground">{info.email}</strong>.
              </CardDescription>
            </div>
          ) : (
            <div className="space-y-1">
              <CardTitle className="font-display text-2xl tracking-tight">This link doesn&apos;t work</CardTitle>
              <CardDescription className="text-base">
                It may have expired (links last 48 hours) or already been used. Ask the account
                owner to send you a new one.
              </CardDescription>
            </div>
          )}
        </CardHeader>
        {info && (
          <CardContent>
            <InviteForm
              token={token}
              secret={info.totp_secret}
              qrSvg={await QRCode.toString(info.otpauth_uri, { type: "svg", margin: 1, width: 144 })}
            />
          </CardContent>
        )}
      </Card>
      <p className="text-center text-xs text-muted-foreground">{COMPANY_IDENTITY_LINE}</p>
    </div>
  )
}
