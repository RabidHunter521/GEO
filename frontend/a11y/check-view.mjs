#!/usr/bin/env node
// frontend/a11y/check-view.mjs
// Accessibility gate for the public client view (/view/[token]/*).
//
// Loads every client-view page against a running app + API with seeded data
// and fails (exit 1) on:
//   - any axe-core WCAG 2.2 A/AA violation, at desktop and at phone width
//   - horizontal page overflow at 375px (the page must not scroll sideways)
//
// Usage:  VIEW_TOKEN=<share token> BASE_URL=http://localhost:3000 node a11y/check-view.mjs
// Optional: SCREENSHOT_DIR=<dir> saves a full-page screenshot per page/width.
// CI runs this in the `a11y` job (.github/workflows/ci.yml) against the
// seeded Medilink demo client.
import { chromium } from "playwright"
import AxeBuilder from "@axe-core/playwright"

const BASE_URL = process.env.BASE_URL ?? "http://localhost:3000"
const TOKEN = process.env.VIEW_TOKEN
const SCREENSHOT_DIR = process.env.SCREENSHOT_DIR
if (!TOKEN) {
  console.error("VIEW_TOKEN is required")
  process.exit(2)
}

export const VIEW_PAGES = [
  "",
  "/progress",
  "/scan",
  "/reputation",
  "/content-plan",
  "/reports",
  "/competitors",
  "/methodology",
]
const WIDTHS = [
  { name: "desktop", width: 1280, height: 900 },
  { name: "phone", width: 375, height: 812 },
]
// wcag22aa adds target-size: tap targets at least 24x24px (WCAG 2.2 AA).
const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]

const browser = await chromium.launch(
  process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {},
)
let failures = 0

for (const vp of WIDTHS) {
  const context = await browser.newContext({
    viewport: { width: vp.width, height: vp.height },
    // Reduced motion so entrance animations can't be caught mid-fade, which
    // would make axe measure contrast against a half-transparent element.
    reducedMotion: "reduce",
  })
  for (const path of VIEW_PAGES) {
    const page = await context.newPage()
    const url = `${BASE_URL}/view/${TOKEN}${path}`
    const label = `${vp.name.padEnd(7)} /view/…${path || "/"}`
    const res = await page.goto(url, { waitUntil: "networkidle" })
    if (!res || res.status() !== 200) {
      console.log(`FAIL ${label}: HTTP ${res?.status()}`)
      failures++
      await page.close()
      continue
    }

    const problems = []
    const { violations } = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze()
    for (const v of violations) {
      const where = v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")
      problems.push(`axe ${v.id} (${v.impact}, ${v.nodes.length} node(s)): ${v.help} → ${where}`)
    }

    if (vp.name === "phone") {
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      )
      if (overflow > 1) problems.push(`horizontal overflow of ${overflow}px at ${vp.width}px`)
    }

    if (SCREENSHOT_DIR) {
      const file = `${SCREENSHOT_DIR}/${vp.name}${path.replace(/\//g, "-") || "-overview"}.png`
      await page.screenshot({ path: file, fullPage: true })
    }

    console.log(`${problems.length ? "FAIL" : "ok  "} ${label}`)
    for (const p of problems) console.log(`       ${p}`)
    failures += problems.length
    await page.close()
  }
  await context.close()
}

await browser.close()
console.log(failures ? `\n${failures} accessibility problem(s)` : "\nAll client-view pages pass")
process.exit(failures ? 1 : 0)
