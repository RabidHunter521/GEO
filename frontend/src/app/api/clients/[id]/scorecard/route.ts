// Server-side proxy for the one-page Scorecard PDF. The backend endpoint is
// admin-only, so the browser can't call it
// directly. This route calls it as the signed-in admin and streams the PDF back.
import { adminAuthHeader } from "@/lib/api-token"
import { NextRequest, NextResponse } from "next/server"

const BASE = process.env.API_BASE_URL ?? "http://localhost:8000"

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  const res = await fetch(`${BASE}/api/v1/clients/${id}/reports/scorecard`, {
    headers: { Authorization: await adminAuthHeader() },
    cache: "no-store",
  })

  if (!res.ok) {
    const message =
      res.status === 404
        ? "No scan data available to build a scorecard yet."
        : `Scorecard generation failed (${res.status}).`
    return NextResponse.json({ error: message }, { status: res.status })
  }

  const pdf = await res.arrayBuffer()
  return new NextResponse(pdf, {
    status: 200,
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition":
        res.headers.get("content-disposition") ?? "attachment; filename=\"SeenBy-Scorecard.pdf\"",
      "Cache-Control": "no-store",
    },
  })
}
