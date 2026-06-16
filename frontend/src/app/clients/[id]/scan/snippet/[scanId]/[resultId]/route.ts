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
  if (!res.ok) return new Response("Not found", { status: 404 })
  return new Response(res.body, { headers: { "Content-Type": "image/png" } })
}
