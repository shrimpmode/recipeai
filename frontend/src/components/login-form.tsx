"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api, ensureCsrfCookie } from "@/lib/api/client";

import { inputClass, primaryButtonClass } from "./ui";

/** Only same-site paths, so `?next=` can't send people to another site. */
function safeNext(raw: string | null): string {
  return raw && raw.startsWith("/") && !raw.startsWith("//") ? raw : "/";
}

export function LoginForm() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  // Warm-up only: onSubmit awaits it again (shared request), so a failure here is retried there.
  useEffect(() => {
    ensureCsrfCookie().catch(() => {});
  }, []);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setPending(true);
    setError(null);
    try {
      await ensureCsrfCookie();
      const { response } = await api.POST("/api/auth/login", {
        body: { username: String(form.get("username")), password: String(form.get("password")) },
      });
      if (response.ok) {
        router.replace(safeNext(new URLSearchParams(window.location.search).get("next")));
        return;
      }
      setError(response.status === 401 ? "That username and password don’t match." : "Couldn’t log in. Try again.");
    } catch {
      setError("Couldn’t reach the server. Try again.");
    }
    setPending(false);
  }

  return (
    <form onSubmit={onSubmit} className="mt-6 space-y-4">
      <div>
        <label htmlFor="username" className="mb-1.5 block text-sm font-medium">
          Username
        </label>
        <input id="username" name="username" autoComplete="username" required className={inputClass} />
      </div>
      <div>
        <label htmlFor="password" className="mb-1.5 block text-sm font-medium">
          Password
        </label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          className={inputClass}
        />
      </div>
      {error && (
        <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">
          {error}
        </p>
      )}
      <button type="submit" disabled={pending} className={`${primaryButtonClass} w-full`}>
        {pending ? "Logging in…" : "Log in"}
      </button>
    </form>
  );
}
