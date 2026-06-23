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

function slug(label: string): string {
  const key = label.toLowerCase().replace(/[^a-z0-9]/g, "")
  return PLATFORM_FILE[key] ?? key
}

export function PlatformIcon({
  label,
  className,
}: {
  label: string
  className?: string
}) {
  const [failed, setFailed] = useState(false)
  if (failed) return null
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={`/platforms/${slug(label)}.png`}
      alt=""
      aria-hidden
      className={cn("h-5 w-5 shrink-0 object-contain", className)}
      onError={() => setFailed(true)}
    />
  )
}
