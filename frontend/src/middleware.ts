// frontend/src/middleware.ts
// Enforces admin login on every page and server action. Without this,
// /auth/login is decorative — Next.js serves all routes to anonymous visitors.
import { NextResponse } from "next/server"
import { auth } from "../auth"

export default auth((req) => {
  // Read-only client view: the 256-bit share token in the URL is the
  // credential — no admin session required (or wanted) here.
  if (req.nextUrl.pathname.startsWith("/view")) {
    return NextResponse.next()
  }

  const isLoggedIn = !!req.auth
  const isLoginPage = req.nextUrl.pathname.startsWith("/auth/login")

  if (!isLoggedIn && !isLoginPage) {
    const loginUrl = new URL("/auth/login", req.nextUrl)
    return NextResponse.redirect(loginUrl)
  }
  if (isLoggedIn && isLoginPage) {
    return NextResponse.redirect(new URL("/clients", req.nextUrl))
  }
  return NextResponse.next()
})

export const config = {
  // Everything except NextAuth's own routes and static assets
  matcher: ["/((?!api/auth|_next/static|_next/image|favicon.ico).*)"],
}
