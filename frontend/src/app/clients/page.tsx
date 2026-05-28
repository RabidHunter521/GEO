// frontend/src/app/clients/page.tsx
import { getClients } from "@/lib/api"
import { ClientCard } from "@/components/clients/ClientCard"

export default async function ClientsPage() {
  const clients = await getClients()

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Clients</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {clients.length} client{clients.length !== 1 ? "s" : ""}
          </p>
        </div>
        {/* AddClientButton added in Task 9 */}
        <button className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm">
          Add Client
        </button>
      </div>

      {clients.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <p className="text-lg font-medium">No clients yet</p>
          <p className="text-sm mt-1">Add your first client to get started.</p>
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
