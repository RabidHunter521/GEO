"use server"

import { redirect } from "next/navigation"
import { acceptInviteLink } from "@/lib/auth-api"

export async function acceptInviteAction(
  token: string,
  _prev: { error: string | null },
  formData: FormData,
): Promise<{ error: string | null }> {
  const password = String(formData.get("password") ?? "")
  const confirm = String(formData.get("confirm") ?? "")
  const code = String(formData.get("code") ?? "")
  if (password !== confirm) return { error: "The two passwords don't match." }
  const result = await acceptInviteLink(token, password, code)
  if (!result.ok) return { error: result.error }
  redirect("/auth/login?welcome=1")
}
