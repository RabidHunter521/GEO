import { describe, expect, it } from "vitest"
import { salutationForHour } from "@/lib/greeting"

describe("salutationForHour", () => {
  it("says good morning from 5 to 11", () => {
    expect(salutationForHour(5)).toBe("Good morning")
    expect(salutationForHour(11)).toBe("Good morning")
  })
  it("says good afternoon from 12 to 17", () => {
    expect(salutationForHour(12)).toBe("Good afternoon")
    expect(salutationForHour(17)).toBe("Good afternoon")
  })
  it("says good evening from 18 through the night to 4", () => {
    expect(salutationForHour(18)).toBe("Good evening")
    expect(salutationForHour(23)).toBe("Good evening")
    expect(salutationForHour(0)).toBe("Good evening")
    expect(salutationForHour(4)).toBe("Good evening")
  })
})
