// frontend/src/app/auth/login/BrandPanel.tsx
// Right-hand brand panel on the login page (desktop only). Mirrors the dark,
// violet-lit hero of seenby.my and shows an illustrative score card so the
// first screen of the app looks like the product. All numbers are sample data
// and the card is labelled as such; nothing here reads real client data.
import { PlatformIcon } from "@/components/view/PlatformIcon"
import { getScoreBand, getScoreColor, type ScoreColor } from "@/lib/score-utils"

const SAMPLE_SCORE = 72
const SAMPLE_TREND = [48, 51, 55, 53, 61, 66, SAMPLE_SCORE]
const SAMPLE_PLATFORMS = [
  { label: "ChatGPT", value: 80 },
  { label: "Perplexity", value: 74 },
  { label: "Gemini", value: 58 },
  { label: "Claude", value: 69 },
]

const RING_CLASS: Record<ScoreColor, string> = {
  green: "stroke-score-strong",
  yellow: "stroke-score-watch",
  red: "stroke-score-low",
}
const TEXT_CLASS: Record<ScoreColor, string> = {
  green: "text-score-strong",
  yellow: "text-score-watch",
  red: "text-score-low",
}
const BAR_CLASS: Record<ScoreColor, string> = {
  green: "bar-strong",
  yellow: "bar-watch",
  red: "bar-low",
}

function ScoreRing({ score }: { score: number }) {
  const radius = 34
  const circumference = 2 * Math.PI * radius
  const color = getScoreColor(score)
  return (
    <div className="relative h-24 w-24 shrink-0">
      <svg viewBox="0 0 80 80" className="h-full w-full -rotate-90">
        <circle cx="40" cy="40" r={radius} fill="none" strokeWidth="7" className="stroke-muted" />
        <circle
          cx="40"
          cy="40"
          r={radius}
          fill="none"
          strokeWidth="7"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - score / 100)}
          className={RING_CLASS[color]}
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center font-display text-3xl font-bold tabular-nums">
        {score}
      </span>
    </div>
  )
}

function Sparkline({ points }: { points: number[] }) {
  const width = 120
  const height = 36
  const min = Math.min(...points)
  const max = Math.max(...points)
  const coords = points.map((p, i) => {
    const x = (i / (points.length - 1)) * width
    const y = height - ((p - min) / (max - min || 1)) * (height - 4) - 2
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-9 w-[120px] overflow-visible">
      <polyline
        points={coords.join(" ")}
        fill="none"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="stroke-primary"
      />
      <circle cx={width} cy={coords[coords.length - 1].split(",")[1]} r="3.5" className="fill-primary" />
    </svg>
  )
}

function SampleScoreCard() {
  const band = getScoreBand(SAMPLE_SCORE)
  const color = getScoreColor(SAMPLE_SCORE)
  const delta = SAMPLE_SCORE - SAMPLE_TREND[0]
  return (
    <div
      aria-hidden
      className="reveal w-full max-w-sm rounded-2xl bg-card p-6 text-card-foreground shadow-brand-lg ring-1 ring-white/10"
      style={{ animationDelay: "250ms" }}
    >
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Growth Readiness
        </p>
        <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          Sample
        </span>
      </div>

      <div className="mt-4 flex items-center gap-5">
        <ScoreRing score={SAMPLE_SCORE} />
        <div className="space-y-2">
          <p className={`text-sm font-semibold capitalize ${TEXT_CLASS[color]}`}>{band.name}</p>
          <Sparkline points={SAMPLE_TREND} />
          <p className="text-xs text-muted-foreground">
            <span className="font-semibold text-score-strong">+{delta} pts</span> in 6 months
          </p>
        </div>
      </div>

      <div className="mt-6 space-y-3 border-t pt-5">
        <p className="text-xs font-medium text-muted-foreground">Visibility frequency</p>
        {SAMPLE_PLATFORMS.map((p) => (
          <div key={p.label} className="flex items-center gap-3">
            <PlatformIcon label={p.label} className="h-4 w-4" />
            <span className="w-20 text-sm">{p.label}</span>
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
              <div
                className={`h-full rounded-full ${BAR_CLASS[getScoreColor(p.value)]}`}
                style={{ width: `${p.value}%` }}
              />
            </div>
            <span className="w-9 text-right text-xs font-medium tabular-nums">{p.value}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function BrandPanel() {
  return (
    <aside className="relative hidden overflow-hidden bg-brand-panel lg:flex lg:flex-col lg:justify-between lg:p-12 xl:p-16">
      <div
        aria-hidden
        className="animate-drift pointer-events-none absolute -left-24 top-1/3 h-96 w-96 rounded-full bg-primary/20 blur-3xl"
      />

      <div className="relative reveal">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary-foreground/60">
          Malaysia&apos;s GEO agency
        </p>
        <h2 className="mt-4 max-w-md text-balance font-display text-5xl font-bold leading-[1.05] tracking-tight text-primary-foreground">
          Your business, <span className="text-primary">seen by AI.</span>
        </h2>
        <p className="mt-4 max-w-sm text-base text-primary-foreground/70">
          AI visibility tracking across ChatGPT, Perplexity, Gemini and Claude — for
          Malaysian businesses.
        </p>
      </div>

      <div className="relative flex justify-center py-10">
        <SampleScoreCard />
      </div>

      <p className="relative text-xs text-primary-foreground/50">
        Scores update every time you run a scan.
      </p>
    </aside>
  )
}
