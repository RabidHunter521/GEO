// frontend/src/components/mirror/AiMirrorTeaser.tsx
// Overview entry point to the AI Mirror. Shows nothing unless there is a pair
// to show.
import Link from "next/link"
import { ArrowRight } from "lucide-react"
import { SectionHeading } from "@/components/view/SectionHeading"
import type { ClientViewMirror, ClientViewMirrorSide } from "@/types"

function verdict(side: ClientViewMirrorSide): string {
  if (side.status === "seen") return "Seen by AI"
  if (side.status === "not_seen") return "Not seen by AI"
  return "No answer recorded"
}

export function AiMirrorTeaser({
  token,
  mirror,
}: {
  token: string
  mirror: ClientViewMirror | null
}) {
  if (!mirror || mirror.status !== "ready" || mirror.platforms.length === 0) return null
  const lead = mirror.platforms[0]

  return (
    <section className="reveal" style={{ animationDelay: "125ms" }}>
      <SectionHeading
        action={
          <Link
            href={`/view/${token}/mirror`}
            className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-primary hover:underline"
          >
            Open the AI Mirror
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        }
      >
        The AI Mirror
      </SectionHeading>
      <Link
        href={`/view/${token}/mirror`}
        className="card-lift block rounded-xl border bg-card p-4"
      >
        <p className="text-sm font-medium text-foreground">
          What {lead.platform_label} says about you, next to {lead.competitor.name}
        </p>
        <div className="mt-2 grid gap-2 text-sm sm:grid-cols-2">
          <p className="text-muted-foreground">
            You: <span className="font-semibold text-foreground">{verdict(lead.you)}</span>
          </p>
          <p className="text-muted-foreground">
            {lead.competitor.name}:{" "}
            <span className="font-semibold text-foreground">{verdict(lead.competitor)}</span>
          </p>
        </div>
      </Link>
    </section>
  )
}
