// frontend/src/components/mirror/AiMirror.tsx
// Day-one AI Mirror: what one AI assistant says about the client, next to what
// it says about their top competitor. Shared by the admin competitors page and
// the client view. Everything shown is Observed: verbatim excerpts of one
// stored answer per side from one check, plus counts from that same check.
// Language rules: "Seen by AI" / "Not seen by AI" only.
import { Quote, TriangleAlert } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { VisibilityBadge } from "@/components/view/VisibilityBadge"
import { PlatformIcon } from "@/components/view/PlatformIcon"
import { evidenceLabel } from "@/lib/product-language"
import { cn, joinWithAnd } from "@/lib/utils"
import type {
  AiMirrorSide,
  ClientViewMirror,
  ClientViewMirrorPlatform,
  ClientViewMirrorSide,
} from "@/types"

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-MY", {
    day: "numeric",
    month: "short",
    year: "numeric",
  })
}

function hasFullAnswer(side: ClientViewMirrorSide): side is AiMirrorSide {
  return "response_text" in side
}

function SideStatus({ side }: { side: ClientViewMirrorSide }) {
  if (side.status === "no_answer") {
    return (
      <Badge variant="outline" className="whitespace-nowrap bg-muted font-medium text-muted-foreground">
        No answer recorded
      </Badge>
    )
  }
  return <VisibilityBadge seen={side.status === "seen"} />
}

function SideCard({
  side,
  role,
  platformLabel,
}: {
  side: ClientViewMirrorSide
  role: string
  platformLabel: string
}) {
  return (
    <div
      className={cn(
        "flex flex-col rounded-xl border bg-card p-4",
        side.status === "seen" ? "border-score-strong/30" : "border-border",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            {role}
          </p>
          <p className="truncate font-display text-lg font-semibold">{side.name}</p>
        </div>
        <SideStatus side={side} />
      </div>
      {side.question && (
        <p className="mt-2 text-xs text-muted-foreground">
          We asked {platformLabel}: &ldquo;{side.question}&rdquo;
        </p>
      )}
      {side.excerpts.length > 0 ? (
        <blockquote className="mt-3 flex gap-2">
          <Quote className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          <div className="space-y-1.5">
            {side.excerpts.map((excerpt, i) => (
              <p key={i} className="text-sm italic leading-relaxed text-foreground/80">
                &ldquo;{excerpt}&rdquo;
              </p>
            ))}
          </div>
        </blockquote>
      ) : (
        <p className="mt-3 text-sm text-muted-foreground">
          {side.status === "no_answer"
            ? `${platformLabel} gave no answer we can show from this check.`
            : "No quotable sentence in this answer."}
        </p>
      )}
      {hasFullAnswer(side) && (
        <div className="mt-3 space-y-2 border-t pt-3">
          {side.flagged_inaccurate && (
            <p className="flex items-center gap-1.5 text-xs font-medium text-score-watch-fg">
              <TriangleAlert className="h-3.5 w-3.5" />
              Flagged as inaccurate: hidden from the client view
            </p>
          )}
          {side.response_text && (
            <details>
              <summary className="cursor-pointer text-xs font-medium text-primary hover:underline">
                Full stored answer (team only)
              </summary>
              <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
                {side.response_text}
              </p>
            </details>
          )}
        </div>
      )}
    </div>
  )
}

function MirrorPair({ pair }: { pair: ClientViewMirrorPlatform }) {
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <SideCard side={pair.you} role="You" platformLabel={pair.platform_label} />
        <SideCard side={pair.competitor} role="Top competitor" platformLabel={pair.platform_label} />
      </div>
      {!pair.same_question && pair.you.question && pair.competitor.question && (
        <p className="text-xs text-muted-foreground">
          The two questions are worded differently, so compare the tone of the
          answers rather than treating this as a like-for-like test.
        </p>
      )}
      {pair.buyer_answers_total > 0 && (
        <p className="rounded-lg border bg-muted/30 px-3 py-2 text-sm">
          Across {pair.buyer_answers_total} answer{pair.buyer_answers_total === 1 ? "" : "s"}{" "}
          {pair.platform_label} gave to buyer questions (like &ldquo;best &hellip; in
          your area&rdquo;), you were seen by AI in{" "}
          <span className="font-semibold tabular-nums">{pair.buyer_answers_you}</span> and{" "}
          {pair.competitor.name} in{" "}
          <span className="font-semibold tabular-nums">{pair.buyer_answers_competitor}</span>.
        </p>
      )}
    </div>
  )
}

export function AiMirror({ mirror }: { mirror: ClientViewMirror }) {
  if (mirror.status === "no_scan") {
    return (
      <div className="rounded-xl border border-dashed bg-card/50 p-8 text-center text-sm text-muted-foreground">
        The AI Mirror appears once the first AI check has finished.
      </div>
    )
  }
  if (mirror.status === "no_competitors") {
    return (
      <div className="rounded-xl border border-dashed bg-card/50 p-8 text-center text-sm text-muted-foreground">
        The AI Mirror needs at least one tracked competitor to compare against.
      </div>
    )
  }
  if (mirror.platforms.length === 0) {
    return (
      <div className="rounded-xl border border-dashed bg-card/50 p-8 text-center text-sm text-muted-foreground">
        The latest check recorded no answers about you or {mirror.competitor_name}.
      </div>
    )
  }

  const [lead, ...others] = mirror.platforms
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5 rounded-full border bg-muted/30 px-2.5 py-0.5 font-medium text-foreground">
          <PlatformIcon label={lead.platform_label} className="h-3.5 w-3.5" />
          {lead.platform_label}
        </span>
        <span>
          {evidenceLabel("observed")}: one answer per side
          {mirror.checked_at && <> from the {formatDate(mirror.checked_at)} check</>}.
          AI answers vary from run to run, so treat this as a snapshot.
        </span>
      </div>
      {mirror.competitor_name && (
        <p className="text-sm text-muted-foreground">
          {mirror.competitor_basis === "buyer_answers"
            ? `${mirror.competitor_name} is the competitor AI assistants put forward most often when we asked buyer questions.`
            : `${mirror.competitor_name} is the competitor seen by AI most often in our tracking.`}
        </p>
      )}
      <MirrorPair pair={lead} />
      {others.length > 0 && (
        <details className="rounded-xl border bg-card p-4">
          <summary className="cursor-pointer text-sm font-medium text-primary hover:underline">
            See what {joinWithAnd(others.map((p) => p.platform_label))}{" "}
            {others.length === 1 ? "says" : "say"}
          </summary>
          <div className="mt-4 space-y-6">
            {others.map((pair) => (
              <div key={pair.platform_label} className="space-y-2">
                <p className="inline-flex items-center gap-1.5 text-sm font-semibold">
                  <PlatformIcon label={pair.platform_label} className="h-4 w-4" />
                  {pair.platform_label}
                </p>
                <MirrorPair pair={pair} />
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  )
}
