"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api/client";
import type { Me } from "@/lib/api/types";

import { ThemeToggle } from "./theme-toggle";
import { quietButtonClass } from "./ui";

// The manual is served by Django itself (staff only), not proxied through Next.
const DOCS_URL = `${process.env.NEXT_PUBLIC_BACKEND_PUBLIC_URL ?? "http://localhost:8000"}/docs/`;

const LINKS = [
  { href: "/", label: "Search" },
  { href: "/goals", label: "Goals" },
] as const;

export function Nav() {
  const pathname = usePathname();
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    let current = true;
    api.GET("/api/auth/me").then(({ data }) => {
      if (current) setMe(data ?? null);
    });
    return () => {
      current = false;
    };
  }, []);

  async function logOut() {
    await api.POST("/api/auth/logout");
    router.replace("/login");
  }

  return (
    <header className="border-b border-line bg-surface">
      <div className="mx-auto flex w-full max-w-3xl items-center justify-between gap-4 px-4 py-4 sm:px-6">
        <div className="flex items-center gap-4 sm:gap-8">
          <Link href="/" className="font-serif text-xl font-medium text-accent">
            Nutrition
          </Link>
          <nav aria-label="Main" className="flex gap-1">
            {LINKS.map(({ href, label }) => {
              const active = pathname === href;
              return (
                <Link
                  key={href}
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={`whitespace-nowrap rounded-lg px-2.5 py-1.5 text-sm transition-colors sm:px-3 ${
                    active ? "bg-accent-soft font-medium text-accent" : "text-muted hover:text-ink"
                  }`}
                >
                  {label}
                </Link>
              );
            })}
          </nav>
        </div>
        <div className="flex items-center gap-3 whitespace-nowrap sm:gap-4">
          {me?.is_staff && (
            <a href={DOCS_URL} className={quietButtonClass}>
              Docs
            </a>
          )}
          {me && <span className="hidden text-sm text-faint sm:inline">{me.username}</span>}
          <ThemeToggle />
          <button type="button" onClick={logOut} className={quietButtonClass}>
            Log out
          </button>
        </div>
      </div>
    </header>
  );
}
