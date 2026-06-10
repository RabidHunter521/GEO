"use client"

import { useEffect, useState } from "react"
import { getScoreBand } from "@/lib/score-utils"
import { cn } from "@/lib/utils"

const BAND_TOKEN: Record<string, string> = {
  green: "var(--score-strong)",
  yellow: "var(--score-watch)",
  red: "var(--score-low)",
}

interface Props {
  score: number | null
  /** Diameter in px */
  size?: number
  /** Stroke width in px */
  stroke?: number
  /** Show the "/ 100" suffix and band label under the number */
  showLabel?: boolean
  className?: string
}

export function ScoreRing({
  score,
  size = 132,
  stroke = 10,
  showLabel = true,
  className,
}: Props) {
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius

  const hasScore = score !== null
  const clamped = hasScore ? Math.max(0, Math.min(100, score!)) : 0
  const band = hasScore ? getScoreBand(clamped) : null
  const color = band ? `hsl(${BAND_TOKEN[band.color]})` : "hsl(var(--muted-foreground))"

  // Animate the stroke drawing in on mount
  const [progress, setProgress] = useState(0)
  useEffect(() => {
    const t = requestAnimationFrame(() => setProgress(clamped))
    return () => cancelAnimationFrame(t)
  }, [clamped])

  const offset = circumference - (progress / 100) * circumference

  return (
    <div
      className={cn("relative inline-flex items-center justify-center", className)}
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="hsl(var(--muted))"
          strokeWidth={stroke}
        />
        {hasScore && (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            style={{ transition: "stroke-dashoffset 900ms cubic-bezier(0.22, 1, 0.36, 1)" }}
          />
        )}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        {hasScore ? (
          <>
            <span className="font-display text-4xl font-bold tabular-nums leading-none text-foreground">
              {clamped.toFixed(0)}
            </span>
            {showLabel && (
              <span className="mt-1 text-xs font-medium text-muted-foreground">
                / 100
              </span>
            )}
          </>
        ) : (
          <span className="text-sm font-medium text-muted-foreground">—</span>
        )}
      </div>
    </div>
  )
}
