import { describe, it, expect } from "vitest"
import { isAuthenticatedAdmin } from "../session-guard"

// Regression guard for GHSA-8fpg-xm3f-6cx3: Auth.js can return an object that
// is truthy but is NOT an authenticated session. Middleware is the only gate in
// front of the admin panel, so every one of these must be rejected.
describe("isAuthenticatedAdmin", () => {
  it("accepts a real session", () => {
    expect(isAuthenticatedAdmin({ user: { email: "admin@seenby.my" } })).toBe(true)
  })

  it.each([
    ["null", null],
    ["undefined", undefined],
    ["empty object", {}],
    ["error-populated auth object", { error: "Configuration" }],
    ["error alongside a user", { error: "JWTSessionError", user: { email: "admin@seenby.my" } }],
    ["session with no user", { user: null }],
    ["user with no email", { user: {} }],
    ["user with empty email", { user: { email: "" } }],
    ["user with non-string email", { user: { email: 123 } }],
  ])("rejects %s", (_label, value) => {
    // Cast: these are deliberately malformed shapes that Auth.js can produce.
    expect(isAuthenticatedAdmin(value as Parameters<typeof isAuthenticatedAdmin>[0])).toBe(false)
  })
})
