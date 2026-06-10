// frontend/src/middleware.ts
// Enforces admin login on every page and server action. Without this,
// /auth/login is decorative — Next.js serves all routes to anonymous visitors.
import { NextResponse } from "next/server"
import { auth } from "../auth"

export default auth((req) => {
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
