"use client"

// frontend/src/components/view/PlatformIcon.tsx
// Maps a platform label (e.g. "ChatGPT") to a logo in /public/platforms.
// Decorative only — the platform name always sits beside it, so the image is
// aria-hidden. If the asset is missing or fails to load (a not-yet-added logo,
// or a brand-new platform), it renders nothing and the card falls back cleanly
// to text-only instead of showing a broken-image icon.
import { useState } from "react"
import { cn } from "@/lib/utils"

const PLATFORM_FILE: Record<string, string> = {
  chatgpt:    "openai",
  perplexity: "perplexity-color",
  gemini:     "gemini-color",
  claude:     "claude-color",
}

// Only platforms with a logo file get an <img>. A server-rendered image can
// fail before hydration attaches onError, which leaves a visible broken-image
// glyph, so platforms without a logo (Google AI surfaces) render text only.
function logoFile(label: string): string | null {
  const key = label.toLowerCase().replace(/[^a-z0-9]/g, "")
  return PLATFORM_FILE[key] ?? null
}

export function PlatformIcon({
  label,
  className,
}: {
  label: string
  className?: string
}) {
  const [failed, setFailed] = useState(false)
  const file = logoFile(label)
  if (failed || !file) return null
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={`/platforms/${file}.png`}
      alt=""
      aria-hidden
      className={cn("h-5 w-5 shrink-0 object-contain", className)}
      onError={() => setFailed(true)}
    />
  )
}
