// frontend/src/app/(admin)/benchmarks/page.tsx
// Portfolio benchmark intelligence — server component.
//
// Global (non-client-scoped), so it lives at the top level of the (admin)
// route group and is served at /benchmarks. See CLAUDE.md section 9.

import { getClientBenchmarks, getClients } from "@/lib/api"
import { CohortHealthPanel } from "@/components/benchmarks/CohortHealthPanel"
import { PortfolioBenchmarkGrid } from "@/components/benchmarks/PortfolioBenchmarkGrid"
import { cohortHealth, opportunityMetrics } from "@/lib/benchmark-display"
import type { BenchmarkComparison } from "@/types"

export const dynamic = "force-dynamic"

interface ClientBenchmarks {
  id: string
  name: string
  comparisons: BenchmarkComparison[]
}

async function loadPortfolio(): Promise<ClientBenchmarks[]> {
  const clients = await getClients()
  // Fetched in parallel rather than sequentially — an admin portfolio is
  // dozens of clients, and serial requests would make the page feel broken.
  // One client's failure must not blank the whole portfolio, so each result
  // degrades to an empty comparison list.
  return Promise.all(
    clients.map(async (client) => {
      try {
        return { id: client.id, name: client.name, comparisons: await getClientBenchmarks(client.id) }
      } catch {
        return { id: client.id, name: client.name, comparisons: [] }
      }
    }),
  )
}

export default async function BenchmarksPage() {
  const portfolio = await loadPortfolio()
  const everything = portfolio.flatMap((entry) => entry.comparisons)
  const health = cohortHealth(everything)
  const withOpportunities = portfolio.filter(
    (entry) => opportunityMetrics(entry.comparisons).length > 0,
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-bold tracking-tight">Benchmarks</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          How each client sits against comparable SeenBy clients, for the last closed month.
          Ranges are published only where a cohort has at least 10 comparable organisations,
          so a withheld figure means missing data — never a poor result.
        </p>
      </div>

      <CohortHealthPanel comparisons={everything} />

      {health.isEmpty ? (
        <p className="rounded-md border border-dashed p-6 text-sm text-muted-foreground">
          No benchmark snapshots have been generated and approved yet. Snapshots are built
          after a month closes, and each one needs review before it appears here.
        </p>
      ) : (
        <>
          {withOpportunities.length > 0 && (
            <section aria-labelledby="opportunity-queue">
              <h2 id="opportunity-queue" className="mb-2 text-lg font-semibold">
                Clients trailing their cohort
              </h2>
              <ul className="space-y-1 text-sm">
                {withOpportunities.map((entry) => (
                  <li key={entry.id}>
                    <a className="underline underline-offset-2" href={`/clients/${entry.id}`}>
                      {entry.name}
                    </a>
                    <span className="text-muted-foreground">
                      {" — "}
                      {opportunityMetrics(entry.comparisons)
                        .map((item) => item.metric_label)
                        .join(", ")}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <div className="space-y-6">
            {portfolio
              .filter((entry) => entry.comparisons.length > 0)
              .map((entry) => (
                <section key={entry.id} aria-labelledby={`client-${entry.id}`}>
                  <h2 id={`client-${entry.id}`} className="mb-2 text-lg font-semibold">
                    {entry.name}
                  </h2>
                  <PortfolioBenchmarkGrid comparisons={entry.comparisons} />
                </section>
              ))}
          </div>
        </>
      )}
    </div>
  )
}
