// frontend/src/app/clients/page.tsx
import { getClients } from "@/lib/api"
import { ClientsManager } from "@/components/clients/ClientsManager"
import { getCurrentAdmin } from "@/lib/current-admin"

export default async function ClientsPage() {
  const [clients, admin] = await Promise.all([getClients(), getCurrentAdmin()])

  return <ClientsManager clients={clients} canArchive={admin.isOwner} />
}
