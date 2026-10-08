import type { Metadata } from "next";

import { LoginForm } from "@/components/login-form";
import { ThemeToggle } from "@/components/theme-toggle";

export const metadata: Metadata = { title: "Log in" };

export default function LoginPage() {
  return (
    <main className="relative flex min-h-screen items-center justify-center px-4">
      <div className="absolute right-4 top-4">
        <ThemeToggle />
      </div>
      <div className="w-full max-w-sm">
        <p className="mb-8 text-center font-serif text-2xl font-medium text-accent">Nutrition</p>
        <div className="rounded-2xl border border-line bg-surface p-8">
          <h1 className="font-serif text-2xl font-medium">Welcome back</h1>
          <p className="mt-1 text-sm text-muted">Log in to find your next meal.</p>
          <LoginForm />
        </div>
      </div>
    </main>
  );
}
