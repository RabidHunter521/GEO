import { NextRequest } from "next/server"

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ scanId: string; resultId: string }> },
) {
  const { scanId, resultId } = await params
  const base = process.env.API_BASE_URL ?? "http://localhost:8000"
  const res = await fetch(
    `${base}/api/v1/scans/${scanId}/results/${resultId}/snippet.png`,
    {
      headers: { Authorization: `Bearer ${process.env.ADMIN_API_KEY}` },
      cache: "no-store",
    },
  )
  if (!res.ok) {
    // Forward the real status (404 = no shareable excerpt; 5xx = backend error)
    // so failures aren't silently masked as "not found".
    return new Response(res.status === 404 ? "Not found" : "Snippet unavailable", {
      status: res.status,
    })
  }
  return new Response(res.body, {
    headers: {
      "Content-Type": "image/png",
      "Content-Disposition": 'inline; filename="seenby-snippet.png"',
    },
  })
}
