// frontend/src/lib/query-segments.ts
// Pure segmentation for progressive disclosure of scan/competitor evidence
// (Phase 1, Task 6). Summaries go before raw evidence; nothing is removed —
// every item passed in still comes back out, in exactly one segment.
//
// The function never reads query text and never guesses commercial intent.
// It only reads the explicit boolean flags the caller supplies per item —
// e.g. "was this seen by AI" and, where a scan-to-scan comparison actually
// exists, "did that change since the last scan". When no comparison data
// exists (e.g. the public client-view surfaces, which don't carry a diff),
// callers should simply omit newlySeen/newlyLost rather than fabricate them.

export interface QuerySegments<T> {
  newlySeen: T[]
  newlyLost: T[]
  opportunities: T[]
  other: T[]
}

export interface QuerySegmentFlags {
  /** Was this query's subject (the client, or a competitor) seen by AI? */
  seen: boolean
  /**
   * Explicit "since last scan" signal: unseen last time, seen now. Leave
   * undefined/false when no prior-scan comparison exists for this item.
   */
  newlySeen?: boolean
  /**
   * Explicit "since last scan" signal: seen last time, unseen now. Leave
   * undefined/false when no prior-scan comparison exists for this item.
   */
  newlyLost?: boolean
}

/**
 * Partitions `items` into four disjoint segments, in priority order:
 * newlySeen > newlyLost > opportunities (unseen) > other (seen, unchanged).
 *
 * The partition is total: the four output arrays always contain exactly the
 * items of `items`, each exactly once, in their original relative order.
 */
export function segmentQueries<T>(
  items: readonly T[],
  getFlags: (item: T) => QuerySegmentFlags,
): QuerySegments<T> {
  const segments: QuerySegments<T> = {
    newlySeen: [],
    newlyLost: [],
    opportunities: [],
    other: [],
  }

  for (const item of items) {
    const { seen, newlySeen, newlyLost } = getFlags(item)
    if (newlySeen) {
      segments.newlySeen.push(item)
    } else if (newlyLost) {
      segments.newlyLost.push(item)
    } else if (!seen) {
      segments.opportunities.push(item)
    } else {
      segments.other.push(item)
    }
  }

  return segments
}

// ── Chip totals ──────────────────────────────────────────────────────────
// A "seen by AI" / "not seen by AI" total shown as a chip must always equal
// a plain filter(brand_detected)-style count elsewhere on the same screen
// (e.g. the Summary stats card) — they are two views of the same
// measurement, never competing counts that can disagree. `other` alone
// undercounts "seen" because segmentQueries's own priority chain moves
// currently-seen rows into `newlySeen` when a comparison exists; likewise
// `opportunities` alone undercounts "not seen" versus `newlyLost`. Sum both
// contributing segments rather than reading either partition member as if it
// were the full total.
export function chipTotals<T>(segments: QuerySegments<T>): { seen: number; notSeen: number } {
  return {
    seen: segments.other.length + segments.newlySeen.length,
    notSeen: segments.opportunities.length + segments.newlyLost.length,
  }
}

// ── Diff applicability ──────────────────────────────────────────────────
// A "since last scan" diff is only meaningful when it was computed against
// the scan currently on screen. `refreshScanAction` (scan/actions.ts) polls
// for a fresh Scan without ever calling revalidatePath, so the server
// component that produced a diff is never re-run — a diff response can
// linger in scope after a newer scan replaces `scan` in state. Because query
// text is template-stable across scans, a stale diff's (platform, category,
// query_text) keys still match plenty of rows in the new scan, so this fails
// confidently (wrong badges) rather than emptily (no badges) if unguarded.
// Fails closed: anything other than an exact match on the scan id currently
// displayed means "no comparison available", never a guess.
export function diffApplies(
  diffLatestScanId: string | null | undefined,
  currentScanId: string | null | undefined,
): boolean {
  return Boolean(diffLatestScanId) && diffLatestScanId === currentScanId
}
