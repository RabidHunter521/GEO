/**
 * Time-of-day salutation for a local hour (0–23). Bands:
 * 5–11 morning, 12–17 afternoon, everything else evening.
 */
export function salutationForHour(hour: number): string {
  if (hour >= 5 && hour < 12) return "Good morning"
  if (hour >= 12 && hour < 18) return "Good afternoon"
  return "Good evening"
}
