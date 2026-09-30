#!/usr/bin/env node
// Generates an ADMIN_TOTP_SECRET for two-factor admin login.
//
//   node scripts/generate-totp-secret.mjs
//
// 1. Add the printed otpauth:// link to your authenticator app (paste it, or
//    turn it into a QR code), or type the secret in manually.
// 2. Set ADMIN_TOTP_SECRET=<secret> on the Railway `frontend` service.
// 3. After the redeploy, the login page asks for the 6-digit code.
// Keep the secret out of git and chat. To switch 2FA off, delete the variable.
import { randomBytes } from "node:crypto"

const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
const bytes = randomBytes(20) // 160 bits, the RFC 4226 recommended length
let bits = 0
let value = 0
let secret = ""
for (const b of bytes) {
  value = (value << 8) | b
  bits += 8
  while (bits >= 5) {
    secret += ALPHABET[(value >>> (bits - 5)) & 31]
    bits -= 5
  }
}

const label = encodeURIComponent("SeenBy:admin")
const url = `otpauth://totp/${label}?secret=${secret}&issuer=SeenBy&algorithm=SHA1&digits=6&period=30`
console.log(`ADMIN_TOTP_SECRET=${secret}\n\nAuthenticator link:\n${url}`)
