// Server wrapper: reads ?welcome=1 (set after an invite link is completed).
import { LoginForm } from "./LoginForm"

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ welcome?: string; ended?: string }>
}) {
  const { welcome, ended } = await searchParams
  return <LoginForm welcome={welcome === "1"} ended={ended === "1"} />
}
