// frontend/src/components/mirror/AiMirrorSection.tsx
// Admin AI Mirror on the competitors page. Same panels the client sees, plus
// the full stored answers and inaccuracy flags so every quote can be checked
// before it is shown on a kickoff call.
import { getAiMirror } from "@/lib/api"
import { AiMirror } from "@/components/mirror/AiMirror"

export async function AiMirrorSection({ clientId }: { clientId: string }) {
  const mirror = await getAiMirror(clientId).catch(() => null)
  if (!mirror) return null
  return (
    <div className="rounded-xl border bg-card px-5 py-4 shadow-brand">
      <div className="mb-4">
        <h3 className="font-display text-lg font-semibold tracking-tight">AI Mirror</h3>
        <p className="mt-0.5 text-sm text-muted-foreground">
          The client next to their top competitor, from the latest scan. The
          client sees the same quotes (never the full answers) on their share
          view under &ldquo;The AI Mirror&rdquo;.
        </p>
      </div>
      <AiMirror mirror={mirror} />
    </div>
  )
}
