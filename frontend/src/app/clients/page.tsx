// frontend/src/app/clients/page.tsx
import { getClients } from "@/lib/api"
import { ClientsManager } from "@/components/clients/ClientsManager"

export default async function ClientsPage() {
  const clients = await getClients()

  return <ClientsManager clients={clients} />
}
