import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Optimistic auth check: no Django session cookie means "go log in". Django
 * stays the authority: an expired session still gets a 401 from the API, and
 * the API client sends the user back here (src/lib/api/client.ts).
 */
export function proxy(request: NextRequest) {
  if (request.cookies.has("sessionid")) {
    return NextResponse.next();
  }
  const login = new URL("/login", request.url);
  const next = request.nextUrl.pathname + request.nextUrl.search;
  if (next !== "/") {
    login.searchParams.set("next", next);
  }
  return NextResponse.redirect(login);
}

export const config = {
  matcher: ["/((?!api/|login|_next/|favicon.ico).*)"],
};
