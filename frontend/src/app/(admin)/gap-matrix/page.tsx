// frontend/src/app/clients/gap-matrix/page.tsx
// Portfolio-level competitor gap matrix — server component.

import { getGapMatrix } from "@/lib/api"
import { GapMatrixTable } from "@/components/clients/GapMatrixTable"

export default async function GapMatrixPage() {
  const matrix = await getGapMatrix()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-bold tracking-tight">Competitor Gap Matrix</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Recommendation and local visibility across all active clients — computed from each
          client&apos;s latest completed scan.
        </p>
      </div>
      <GapMatrixTable matrix={matrix} />
    </div>
  )
}
