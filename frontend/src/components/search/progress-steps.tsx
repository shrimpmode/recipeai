import type { SearchStep } from "@/lib/api/types";

import { LiveTimer } from "./live-timer";

// The API sends step codes; the words the user reads live here (spec FR-008).
const STEP_LABELS: Record<SearchStep, string> = {
  understanding: "Understanding your request",
  searching: "Searching recipes",
  widening: "Widening the search",
  checking: "Checking against your goals",
  choosing: "Choosing the best matches",
};

/** The steps an AI search has started, the last one running. Only steps that actually ran are listed. */
export function ProgressSteps({ steps, startedAt }: { steps: SearchStep[]; startedAt: number }) {
  return (
    <ol className="space-y-2.5 rounded-2xl border border-line bg-surface px-5 py-4" aria-label="Search progress">
      {steps.map((step, i) => {
        const running = i === steps.length - 1;
        return (
          <li key={step} className="flex items-center gap-3">
            {running ? (
              <span className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-accent border-t-transparent motion-reduce:animate-none" />
            ) : (
              <span
                className="grid h-4 w-4 shrink-0 place-items-center rounded-full bg-accent text-[10px] text-accent-ink"
                aria-hidden="true"
              >
                ✓
              </span>
            )}
            <span className={running ? "flex-1 font-medium" : "flex-1 text-muted"}>
              {STEP_LABELS[step]}
              {!running && <span className="sr-only"> (done)</span>}
            </span>
            {running && <LiveTimer startedAt={startedAt} />}
          </li>
        );
      })}
    </ol>
  );
}
