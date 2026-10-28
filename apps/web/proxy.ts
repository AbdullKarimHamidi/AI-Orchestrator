import { NextResponse, type NextRequest } from "next/server"

/**
 * Optimistic redirect only: sends visitors without a session cookie to /login.
 * This is NOT authorization. FastAPI validates the session and workspace membership
 * on every API request; a forged cookie gets nothing but 401s.
 */
const PUBLIC = ["/login", "/register", "/invite"]

export function proxy(req: NextRequest) {
  const { pathname, search } = req.nextUrl
  if (PUBLIC.some((p) => pathname.startsWith(p))) return NextResponse.next()
  if (!req.cookies.has("orch_session")) {
    const url = req.nextUrl.clone()
    url.pathname = "/login"
    url.search = pathname === "/" ? "" : `?next=${encodeURIComponent(pathname + search)}`
    return NextResponse.redirect(url)
  }
  return NextResponse.next()
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
}
