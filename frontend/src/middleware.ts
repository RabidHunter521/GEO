// frontend/src/middleware.ts
// Two jobs, both security-critical:
//  1. Enforces admin login on every page and server action. Without this,
//     /auth/login is decorative — Next.js serves all routes to anonymous visitors.
//  2. Issues a per-request CSP nonce. The policy lives here rather than in
//     next.config.ts because a nonce has to be minted per response; a static
//     header can only ever say 'unsafe-inline', which defeats the point.
import { NextResponse } from "next/server"
import { auth } from "../auth"

// React Refresh compiles with eval in development; production never needs it.
const isDev = process.env.NODE_ENV !== "production"

function buildCsp(nonce: string): string {
  return [
    "default-src 'self'",
    // 'strict-dynamic' lets the nonced Next.js bootstrap load its own chunks,
    // and makes CSP3 browsers ignore the 'self' fallback here — so only scripts
    // this specific response vouched for can execute. That is what closes the
    // injected-<script> path that 'unsafe-inline' used to leave open.
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isDev ? " 'unsafe-eval'" : ""}`,
    // Styles deliberately keep 'unsafe-inline'. next/font and Radix inject
    // style tags we cannot nonce, and an injected stylesheet is a far weaker
    // vector than script execution. Revisit only if a style-based leak matters.
    "style-src 'self' 'unsafe-inline'",
    // https: stays for R2-hosted client logos on the public view.
    "img-src 'self' data: https:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ")
}

export default auth((req) => {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64")
  const csp = buildCsp(nonce)

  // The nonce reaches the renderer as a request header — Next.js reads it and
  // stamps its own script tags with it.
  const requestHeaders = new Headers(req.headers)
  requestHeaders.set("x-nonce", nonce)
  requestHeaders.set("Content-Security-Policy", csp)

  const proceed = () => {
    const res = NextResponse.next({ request: { headers: requestHeaders } })
    res.headers.set("Content-Security-Policy", csp)
    return res
  }

  // Read-only client view: the 256-bit share token in the URL is the
  // credential — no admin session required (or wanted) here.
  if (req.nextUrl.pathname.startsWith("/view")) {
    return proceed()
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
  return proceed()
})

export const config = {
  // Everything except NextAuth's own routes and static assets
  matcher: ["/((?!api/auth|_next/static|_next/image|favicon.ico).*)"],
}
