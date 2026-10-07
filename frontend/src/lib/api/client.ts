import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "./schema";

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

function readCookie(name: string): string | undefined {
  return document.cookie
    .split("; ")
    .find((cookie) => cookie.startsWith(`${name}=`))
    ?.slice(name.length + 1);
}

/** Django's CSRF protection: echo the `csrftoken` cookie in a header on unsafe requests. */
const csrfHeader: Middleware = {
  onRequest({ request }) {
    const token = readCookie("csrftoken");
    if (token && !SAFE_METHODS.has(request.method)) {
      request.headers.set("X-CSRFToken", token);
    }
    return request;
  },
};

/** A 401 anywhere but the login call means the session is gone: start over at /login. */
const redirectWhenSignedOut: Middleware = {
  onResponse({ request, response }) {
    if (response.status === 401 && !new URL(request.url).pathname.startsWith("/api/auth/")) {
      const next = window.location.pathname + window.location.search;
      // Runs outside React (no router here); a full load also drops any state left from the old session.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.assign(`/login?next=${encodeURIComponent(next)}`);
    }
    return response;
  },
};

/** Typed client for the Django API (types generated from its OpenAPI schema: `pnpm gen:api`).
 * Browser-only: requests go to this origin's /api, which next.config.ts proxies to Django. */
export const api = createClient<paths>({ baseUrl: "" });
api.use(csrfHeader, redirectWhenSignedOut);

export async function ensureCsrfCookie(): Promise<void> {
  if (!readCookie("csrftoken")) {
    await api.GET("/api/auth/csrf");
  }
}
