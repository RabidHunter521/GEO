// frontend/src/app/clients/page.tsx
import { getClients } from "@/lib/api"
import { ClientCard } from "@/components/clients/ClientCard"
import { AddClientButton } from "@/components/clients/AddClientButton"

export default async function ClientsPage() {
  const clients = await getClients()

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight">Clients</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {clients.length} client{clients.length !== 1 ? "s" : ""}
          </p>
        </div>
        <AddClientButton />
      </div>

      {clients.length === 0 ? (
        <div className="rounded-xl border border-dashed bg-card/50 py-16 text-center">
          <p className="font-display text-lg font-semibold">No clients yet</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Add your first client to get started.
          </p>
          <div className="mt-4 flex justify-center">
            <AddClientButton />
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {clients.map((client) => (
            <ClientCard key={client.id} client={client} />
          ))}
        </div>
      )}
    </div>
  )
}
