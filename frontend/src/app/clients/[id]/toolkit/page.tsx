import { getToolkitFiles, getClient } from "@/lib/api"
import { ToolkitClient } from "./ToolkitClient"

interface Props {
  params: Promise<{ id: string }>
}

export default async function ToolkitPage({ params }: Props) {
  const { id } = await params
  let files = null
  let clientWebsite = ""
  try {
    const [fetchedFiles, client] = await Promise.all([
      getToolkitFiles(id),
      getClient(id),
    ])
    files = fetchedFiles
    clientWebsite = client.website
  } catch {
    // Backend down or client not found — show empty state
  }
  return <ToolkitClient clientId={id} initialFiles={files} clientWebsite={clientWebsite} />
}
