import { describe, expect, it } from "vitest"
import { base32Decode, base32Encode, hotp, verifyTotp } from "@/lib/totp"

// RFC 6238 Appendix B, SHA-1 seed "12345678901234567890".
const SECRET = base32Encode(new TextEncoder().encode("12345678901234567890"))

describe("totp", () => {
  it("round-trips base32", () => {
    expect(SECRET).toBe("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ")
    expect(new TextDecoder().decode(base32Decode(SECRET))).toBe("12345678901234567890")
  })

  it("matches the RFC 6238 test vectors", async () => {
    const key = base32Decode(SECRET)
    expect(await hotp(key, Math.floor(59 / 30), 8)).toBe("94287082")
    expect(await hotp(key, Math.floor(1111111109 / 30), 8)).toBe("07081804")
    expect(await hotp(key, Math.floor(1234567890 / 30), 8)).toBe("89005924")
    expect(await hotp(key, Math.floor(20000000000 / 30), 8)).toBe("65353130")
  })

  it("verifies the current code and one step of drift, not two", async () => {
    const now = 1234567890 * 1000
    const key = base32Decode(SECRET)
    const step = Math.floor(1234567890 / 30)
    expect(await verifyTotp(SECRET, await hotp(key, step), now)).toBe(step)
    expect(await verifyTotp(SECRET, await hotp(key, step - 1), now)).toBe(step - 1)
    expect(await verifyTotp(SECRET, await hotp(key, step + 1), now)).toBe(step + 1)
    expect(await verifyTotp(SECRET, await hotp(key, step - 2), now)).toBeNull()
  })

  it("rejects malformed codes", async () => {
    expect(await verifyTotp(SECRET, "12345", 0)).toBeNull()
    expect(await verifyTotp(SECRET, "abcdef", 0)).toBeNull()
    expect(await verifyTotp(SECRET, "", 0)).toBeNull()
  })
})
