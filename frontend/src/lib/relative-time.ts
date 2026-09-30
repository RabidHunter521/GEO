// frontend/src/lib/relative-time.ts
// "2 days ago"-style phrasing for admin surfaces. Backend timestamps are naive
// UTC (timestamp-without-tz), so a bare ISO string is read as UTC.

export function parseUtc(iso: string): Date {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`)
}

export function timeAgo(iso: string, now: Date = new Date()): string {
  const seconds = Math.max(0, Math.round((now.getTime() - parseUtc(iso).getTime()) / 1000))
  if (seconds < 60) return "just now"
  const units: [number, string][] = [
    [60 * 60 * 24 * 365, "year"],
    [60 * 60 * 24 * 30, "month"],
    [60 * 60 * 24 * 7, "week"],
    [60 * 60 * 24, "day"],
    [60 * 60, "hour"],
    [60, "minute"],
  ]
  for (const [size, unit] of units) {
    const n = Math.floor(seconds / size)
    if (n >= 1) return `${n} ${unit}${n === 1 ? "" : "s"} ago`
  }
  return "just now"
}
