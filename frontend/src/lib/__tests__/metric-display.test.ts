import { describe, expect, it } from "vitest"
import { formatMetricDelta, formatMetricValue } from "../metric-display"

describe("formatMetricValue", () => {
  it("renders null as an honest dash, never a fabricated 0", () => {
    const result = formatMetricValue(null, "score")
    expect(result.display).toBe("—")
    expect(result.color).toBeNull()
  })

  it("renders a stored 0 as the digit, not as missing data", () => {
    const result = formatMetricValue(0, "score")
    expect(result.display).toBe("0")
  })

  it("produces different output for 0 than for null (the whole point)", () => {
    const zero = formatMetricValue(0, "score")
    const missing = formatMetricValue(null, "score")
    expect(zero.display).not.toBe(missing.display)
  })

  it("renders a positive value rounded, with thousands separators", () => {
    const result = formatMetricValue(1234.6, "count")
    expect(result.display).toBe("1,235")
  })

  it("color-bands score variants but never count variants", () => {
    expect(formatMetricValue(10, "score").color).toBe("red")
    expect(formatMetricValue(90, "score").color).toBe("green")
    expect(formatMetricValue(90, "count").color).toBeNull()
  })
})

describe("formatMetricDelta", () => {
  it("renders null delta as null (no prior period to compare)", () => {
    expect(formatMetricDelta(null, "score")).toBeNull()
  })

  it("renders a real 0 delta as a flat, non-null result", () => {
    const result = formatMetricDelta(0, "score")
    expect(result).not.toBeNull()
    expect(result?.direction).toBe("flat")
  })

  it("produces different output for a 0 delta than for a null delta (the whole point)", () => {
    const zero = formatMetricDelta(0, "score")
    const missing = formatMetricDelta(null, "score")
    expect(zero).not.toBeNull()
    expect(missing).toBeNull()
  })

  it("does not prefix a flat delta with a '+' — that would read as positive movement", () => {
    const result = formatMetricDelta(0, "score")
    expect(result?.display).not.toMatch(/^\+/)
    expect(result?.display).toBe("0.0")
  })

  it("marks a positive delta as up and prefixes it with '+'", () => {
    const result = formatMetricDelta(2.4, "score")
    expect(result?.direction).toBe("up")
    expect(result?.display).toBe("+2.4")
  })

  it("marks a negative delta as down without a double sign", () => {
    const result = formatMetricDelta(-3.1, "score")
    expect(result?.direction).toBe("down")
    expect(result?.display).toBe("-3.1")
  })

  it("formats count-variant deltas as rounded integers, not decimals", () => {
    const up = formatMetricDelta(12.7, "count")
    expect(up?.display).toBe("+13")
    const flat = formatMetricDelta(0, "count")
    expect(flat?.display).toBe("0")
  })
})
