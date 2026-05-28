// frontend/src/app/clients/[id]/layout.tsx
import { notFound } from "next/navigation"
import { getClient } from "@/lib/api"

export default async function ClientLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  let client
  try {
    client = await getClient(id)
  } catch {
    notFound()
  }

  return (
    <div>
      <div className="mb-6 pb-4 border-b">
        <h1 className="text-xl font-semibold">{client.name}</h1>
        <p className="text-sm text-muted-foreground">
          <a
            href={client.website}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:underline"
          >
            {client.website}
          </a>
          {" · "}
          {client.industry}
        </p>
      </div>
      {children}
    </div>
  )
}
