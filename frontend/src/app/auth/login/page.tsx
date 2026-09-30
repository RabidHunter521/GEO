// Server wrapper so the form knows whether two-factor is switched on without
// exposing the secret: only the boolean crosses to the client.
import { LoginForm } from "./LoginForm"

export default function LoginPage() {
  return <LoginForm totpEnabled={Boolean(process.env.ADMIN_TOTP_SECRET)} />
}
