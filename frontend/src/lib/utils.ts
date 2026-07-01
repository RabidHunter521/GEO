import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// Copies text to the clipboard, returning whether it actually succeeded.
// navigator.clipboard is undefined on insecure origins (e.g. a LAN IP over
// http), so callers must check the result before claiming "Copied" — a legacy
// execCommand fallback covers those contexts where possible.
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // permission denied / not focused — try the legacy path below
  }
  try {
    const ta = document.createElement("textarea")
    ta.value = text
    ta.style.position = "fixed"
    ta.style.opacity = "0"
    document.body.appendChild(ta)
    ta.focus()
    ta.select()
    const ok = document.execCommand("copy")
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}

// True when `raw` looks like a real website. Accepts a bare host ("rival.com")
// by assuming https, and requires a dotted hostname so junk like "banana" is
// rejected. Empty is the caller's concern (optional fields).
export function isValidWebsite(raw: string): boolean {
  const v = raw.trim()
  if (!v) return false
  try {
    const u = new URL(/^https?:\/\//i.test(v) ? v : `https://${v}`)
    return u.hostname.includes(".")
  } catch {
    return false
  }
}

// "A", "A and B", "A, B and C" — for listing enabled platforms in prose.
export function joinWithAnd(items: string[]): string {
  if (items.length <= 1) return items[0] ?? ""
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`
}
