import ChecklistClient from "./ChecklistClient"

export default async function ChecklistPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  return <ChecklistClient clientId={id} />
}
