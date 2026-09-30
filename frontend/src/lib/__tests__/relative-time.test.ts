import { describe, expect, it } from "vitest"
import { parseUtc, timeAgo } from "@/lib/relative-time"

const now = new Date("2026-09-30T12:00:00Z")

describe("timeAgo", () => {
  it("reads naive backend timestamps as UTC", () => {
    expect(parseUtc("2026-09-30T10:00:00").toISOString()).toBe("2026-09-30T10:00:00.000Z")
  })
  it("phrases recent and older opens", () => {
    expect(timeAgo("2026-09-30T11:59:30", now)).toBe("just now")
    expect(timeAgo("2026-09-30T11:00:00", now)).toBe("1 hour ago")
    expect(timeAgo("2026-09-28T12:00:00", now)).toBe("2 days ago")
    expect(timeAgo("2026-09-16T12:00:00Z", now)).toBe("2 weeks ago")
  })
  it("never goes negative on clock skew", () => {
    expect(timeAgo("2026-09-30T12:05:00", now)).toBe("just now")
  })
})
