// frontend/src/lib/totp.ts
// RFC 6238 TOTP (SHA-1, 6 digits, 30 s steps): the codes Google Authenticator,
// 1Password, Authy etc. produce. Uses Web Crypto only, so it runs in both the
// Node and edge runtimes (auth.ts is also bundled into middleware).

const BASE32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
export const TOTP_STEP_SECONDS = 30
export const TOTP_DIGITS = 6

export function base32Decode(input: string): Uint8Array {
  const clean = input.toUpperCase().replace(/[\s=-]/g, "")
  let bits = 0
  let value = 0
  const out: number[] = []
  for (const ch of clean) {
    const idx = BASE32.indexOf(ch)
    if (idx === -1) throw new Error("Invalid base32 character in TOTP secret")
    value = (value << 5) | idx
    bits += 5
    if (bits >= 8) {
      out.push((value >>> (bits - 8)) & 0xff)
      bits -= 8
    }
  }
  return new Uint8Array(out)
}

export function base32Encode(bytes: Uint8Array): string {
  let bits = 0
  let value = 0
  let out = ""
  for (const b of bytes) {
    value = (value << 8) | b
    bits += 8
    while (bits >= 5) {
      out += BASE32[(value >>> (bits - 5)) & 31]
      bits -= 5
    }
  }
  if (bits > 0) out += BASE32[(value << (5 - bits)) & 31]
  return out
}

export async function hotp(key: Uint8Array, counter: number, digits = TOTP_DIGITS): Promise<string> {
  const msg = new Uint8Array(8)
  let c = counter
  for (let i = 7; i >= 0; i--) {
    msg[i] = c & 0xff
    c = Math.floor(c / 256)
  }
  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    key as BufferSource,
    { name: "HMAC", hash: "SHA-1" },
    false,
    ["sign"],
  )
  const mac = new Uint8Array(await crypto.subtle.sign("HMAC", cryptoKey, msg))
  const offset = mac[mac.length - 1] & 0x0f
  const bin =
    ((mac[offset] & 0x7f) << 24) |
    (mac[offset + 1] << 16) |
    (mac[offset + 2] << 8) |
    mac[offset + 3]
  return (bin % 10 ** digits).toString().padStart(digits, "0")
}

/**
 * Returns the matched time-step counter, or null. Accepts ±`window` steps for
 * clock drift. The caller rejects a counter it has already accepted (replay).
 */
export async function verifyTotp(
  secretBase32: string,
  code: string,
  nowMs: number = Date.now(),
  window = 1,
): Promise<number | null> {
  const normalized = code.replace(/\s/g, "")
  if (!/^\d{6}$/.test(normalized)) return null
  const key = base32Decode(secretBase32)
  const current = Math.floor(nowMs / 1000 / TOTP_STEP_SECONDS)
  let matched: number | null = null
  // Check every candidate (no early return) so timing does not reveal which
  // step matched.
  for (let step = current - window; step <= current + window; step++) {
    const expected = await hotp(key, step)
    let diff = 0
    for (let i = 0; i < TOTP_DIGITS; i++) diff |= expected.charCodeAt(i) ^ normalized.charCodeAt(i)
    if (diff === 0 && matched === null) matched = step
  }
  return matched
}
