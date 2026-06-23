// Server-side proxy for the one-page Scorecard PDF. The backend endpoint is
// gated by ADMIN_API_KEY (a server-only env var), so the browser can't call it
// directly — this route attaches the key and streams the PDF back as a download.
import { NextRequest, NextResponse } from "next/server"

const BASE = process.env.API_BASE_URL ?? "http://localhost:8000"

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  const res = await fetch(`${BASE}/api/v1/clients/${id}/reports/scorecard`, {
    headers: { Authorization: `Bearer ${process.env.ADMIN_API_KEY}` },
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
