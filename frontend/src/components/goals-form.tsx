"use client";

import { useEffect, useState } from "react";

import { api, ensureCsrfCookie } from "@/lib/api/client";
import type { Goals } from "@/lib/api/types";

import { inputClass, primaryButtonClass } from "./ui";

type GoalField = keyof Goals;

const FIELDS: { name: GoalField; label: string; unit: string; dot: string }[] = [
  { name: "daily_calorie_target", label: "Calories", unit: "kcal", dot: "bg-ink" },
  { name: "protein_target_g", label: "Protein", unit: "g", dot: "bg-protein" },
  { name: "carbs_target_g", label: "Carbs", unit: "g", dot: "bg-carbs" },
  { name: "fat_target_g", label: "Fat", unit: "g", dot: "bg-fat" },
  { name: "fiber_target_g", label: "Fiber", unit: "g", dot: "bg-fiber" },
];

type Status = { kind: "loading" } | { kind: "ready" } | { kind: "saved" } | { kind: "error"; message: string };

export function GoalsForm() {
  const [values, setValues] = useState<Record<GoalField, string> | null>(null);
  const [status, setStatus] = useState<Status>({ kind: "loading" });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    // A response for a discarded effect (StrictMode remount, unmount) must not overwrite what the user has typed.
    let current = true;
    api.GET("/api/profile").then(({ data }) => {
      if (!current) return;
      if (!data) {
        setStatus({ kind: "error", message: "Couldn’t load your goals." });
        return;
      }
      setValues(
        Object.fromEntries(FIELDS.map(({ name }) => [name, data[name]?.toString() ?? ""])) as Record<
          GoalField,
          string
        >,
      );
      setStatus({ kind: "ready" });
    });
    return () => {
      current = false;
    };
  }, []);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!values) return;
    setSaving(true);
    const body = Object.fromEntries(
      FIELDS.map(({ name }) => [name, values[name].trim() === "" ? null : Number(values[name])]),
    ) as Goals;
    await ensureCsrfCookie();
    const { response } = await api.PUT("/api/profile", { body });
    setSaving(false);
    setStatus(
      response.ok
        ? { kind: "saved" }
        : { kind: "error", message: "Couldn’t save. Targets must be between 0 and 20,000." },
    );
  }

  if (!values) {
    return status.kind === "error" ? (
      <p role="alert" className="rounded-2xl bg-danger-soft px-5 py-4 text-danger">
        {status.message}
      </p>
    ) : (
      <div className="h-80 animate-pulse rounded-2xl bg-sunken" />
    );
  }

  return (
    <form onSubmit={onSubmit} className="rounded-2xl border border-line bg-surface p-6 sm:p-8">
      <div className="grid gap-5 sm:grid-cols-2">
        {FIELDS.map(({ name, label, unit, dot }) => (
          <div key={name}>
            <label htmlFor={name} className="mb-1.5 flex items-center gap-2 text-sm font-medium">
              <span className={`h-2 w-2 rounded-full ${dot}`} aria-hidden="true" />
              {label}
              <span className="font-normal text-faint">({unit} per day)</span>
            </label>
            <input
              id={name}
              name={name}
              type="number"
              inputMode="decimal"
              min={0}
              max={20000}
              step="any"
              placeholder="No target"
              value={values[name]}
              onChange={(event) => {
                const value = event.target.value;
                // Functional update: edits to several fields before a re-render must not overwrite each other.
                setValues((current) => (current ? { ...current, [name]: value } : current));
                setStatus({ kind: "ready" });
              }}
              className={inputClass}
            />
          </div>
        ))}
      </div>
      <div className="mt-8 flex items-center gap-4">
        <button type="submit" disabled={saving} className={primaryButtonClass}>
          {saving ? "Saving…" : "Save goals"}
        </button>
        <p aria-live="polite" className="text-sm">
          {status.kind === "saved" && <span className="text-accent">Saved.</span>}
          {status.kind === "error" && <span className="text-danger">{status.message}</span>}
        </p>
      </div>
    </form>
  );
}
