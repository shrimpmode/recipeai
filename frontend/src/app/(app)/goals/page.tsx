import type { Metadata } from "next";

import { GoalsForm } from "@/components/goals-form";

export const metadata: Metadata = { title: "Goals" };

export default function GoalsPage() {
  return (
    <>
      <header className="mb-8">
        <h1 className="font-serif text-4xl font-medium tracking-tight">Nutrition goals</h1>
        <p className="mt-3 max-w-xl text-muted">
          Daily targets. AI search favours recipes close to a third of each, one meal&rsquo;s share. Every field is
          optional.
        </p>
      </header>
      <GoalsForm />
    </>
  );
}
