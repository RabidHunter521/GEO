// Server-side proxy for the 90-day review deck PDF. The backend endpoint is
// admin-only, so the browser can't call it directly. This route calls it as
// the signed-in admin and streams the PDF back. ?mode=case_study returns the
// anonymised sales case-study version; anything else falls back to the client
// version.
import { adminAuthHeader } from "@/lib/api-token"
import { NextRequest, NextResponse } from "next/server"

const BASE = process.env.API_BASE_URL ?? "http://localhost:8000"

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  const mode = req.nextUrl.searchParams.get("mode") === "case_study" ? "case_study" : "client"
  const res = await fetch(
    `${BASE}/api/v1/clients/${id}/reports/review-deck?mode=${mode}`,
    {
      headers: { Authorization: await adminAuthHeader() },
      cache: "no-store",
    },
  )

  if (!res.ok) {
    const message =
      res.status === 404
        ? "No scan data available to build a review deck yet."
        : `Review deck generation failed (${res.status}).`
    return NextResponse.json({ error: message }, { status: res.status })
  }

  const pdf = await res.arrayBuffer()
  return new NextResponse(pdf, {
    status: 200,
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition":
        res.headers.get("content-disposition") ??
        "attachment; filename=\"SeenBy-90-Day-Review.pdf\"",
      "Cache-Control": "no-store",
    },
  })
}
