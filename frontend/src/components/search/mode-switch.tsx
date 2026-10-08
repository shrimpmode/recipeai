"use client";

export type SearchMode = "ai" | "keyword";

const MODES: { value: SearchMode; label: string }[] = [
  { value: "ai", label: "AI search" },
  { value: "keyword", label: "Keyword search" },
];

export function ModeSwitch({ mode, onChange }: { mode: SearchMode; onChange: (mode: SearchMode) => void }) {
  return (
    <fieldset className="inline-flex rounded-xl bg-sunken p-1">
      <legend className="sr-only">Search mode</legend>
      {MODES.map(({ value, label }) => {
        const checked = mode === value;
        return (
          <label
            key={value}
            className={`cursor-pointer rounded-lg px-4 py-2 text-sm font-medium transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent ${
              checked ? "bg-surface text-ink" : "text-muted hover:text-ink"
            }`}
          >
            <input
              type="radio"
              name="search-mode"
              value={value}
              checked={checked}
              onChange={() => onChange(value)}
              className="sr-only"
            />
            {label}
          </label>
        );
      })}
    </fieldset>
  );
}
