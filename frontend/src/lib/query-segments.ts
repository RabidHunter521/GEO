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
