// Reached when the API rejects the signed-in admin (deactivated, or their
// sign-in was reset). Clears the Auth.js session and lands on the login page;
// without this the login page would bounce a still-"signed-in" admin back
// into pages that can no longer load.
import { signOut } from "../../../../auth"

export async function GET() {
  await signOut({ redirectTo: "/auth/login?ended=1" })
}
