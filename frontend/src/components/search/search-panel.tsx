"use client";

import { useEffect, useRef, useState } from "react";

import { api, ensureCsrfCookie } from "@/lib/api/client";
import type { AiRecipe, KeywordRecipe, QueryResult } from "@/lib/api/types";
import { formatDuration } from "@/lib/format";

import { RecipeCard, type RecipeCardData } from "../recipe-card";
import { inputClass, primaryButtonClass } from "../ui";
import { LiveTimer } from "./live-timer";
import { ModeSwitch, type SearchMode } from "./mode-switch";

const POLL_INTERVAL_MS = 1000;
// The worker retries Claude with backoff (2 + 4 + 8 s) before giving up; allow for that plus queueing.
const AI_SEARCH_TIMEOUT_MS = 90_000;

const COPY = {
  ai: {
    label: "Describe what you feel like eating",
    placeholder: "Something warm and high in fibre for lunch",
    submit: "Ask",
  },
  keyword: {
    label: "Search recipe names and ingredients",
    placeholder: "Recipe name or ingredients, e.g. chicken lemon",
    submit: "Search",
  },
} satisfies Record<SearchMode, Record<string, string>>;

type View =
  | { kind: "idle" }
  | { kind: "searching"; mode: SearchMode; startedAt: number }
  | { kind: "results"; mode: SearchMode; query: string; recipes: RecipeCardData[]; elapsedMs: number }
  | { kind: "error"; message: string };

class SearchFailed extends Error {}

function fromKeyword(recipe: KeywordRecipe): RecipeCardData {
  return {
    name: recipe.recipe_name,
    sourceUrl: recipe.source_url,
    imageUrl: recipe.image_url,
    calories: recipe.calories_per_serving,
    protein: recipe.protein_g_per_serving,
    carbs: recipe.carbs_g_per_serving,
    fat: recipe.fat_g_per_serving,
    fiber: recipe.fiber_g_per_serving,
    sugar: recipe.sugar_g_per_serving,
    sodiumMg: recipe.sodium_mg_per_serving,
  };
}

function fromAi(recipe: AiRecipe): RecipeCardData {
  return { ...fromKeyword({ ...recipe, id: recipe.recipe_id }), description: recipe.description };
}

const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

export function SearchPanel() {
  const [mode, setMode] = useState<SearchMode>("ai");
  const [view, setView] = useState<View>({ kind: "idle" });
  // Each search takes a ticket; results from a superseded search (or after unmount) are dropped.
  const ticket = useRef(0);

  useEffect(() => {
    return () => {
      ticket.current += 1;
    };
  }, []);

  async function keywordSearch(q: string) {
    const { data } = await api.GET("/api/search", { params: { query: { q } } });
    if (!data) throw new SearchFailed("Search failed. Try again.");
    return { recipes: data.results.map(fromKeyword), elapsedMs: data.elapsed_ms };
  }

  async function aiSearch(prompt: string, myTicket: number) {
    await ensureCsrfCookie();
    const submitted = await api.POST("/api/queries", { body: { prompt } });
    if (!submitted.data) throw new SearchFailed("Couldn’t start the search. Try again.");

    let query: QueryResult = submitted.data;
    const deadline = performance.now() + AI_SEARCH_TIMEOUT_MS;
    while (query.status === "pending" || query.status === "running") {
      if (ticket.current !== myTicket) return null;
      if (performance.now() > deadline) throw new SearchFailed("This is taking too long. Try again in a moment.");
      await sleep(POLL_INTERVAL_MS);
      const polled = await api.GET("/api/queries/{query_request_id}", {
        params: { path: { query_request_id: query.id } },
      });
      if (!polled.data) throw new SearchFailed("Lost track of the search. Try again.");
      query = polled.data;
    }
    if (query.status === "error" || !query.results) {
      throw new SearchFailed("Something went wrong finding recipes for that request. Please try again.");
    }
    return { recipes: query.results.map(fromAi), elapsedMs: (query.elapsed_seconds ?? 0) * 1000 };
  }

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = String(new FormData(event.currentTarget).get("q") ?? "").trim();
    if (!text) return;

    const myTicket = ++ticket.current;
    const searchMode = mode;
    setView({ kind: "searching", mode: searchMode, startedAt: performance.now() });
    try {
      const outcome = searchMode === "ai" ? await aiSearch(text, myTicket) : await keywordSearch(text);
      if (outcome && ticket.current === myTicket) {
        setView({ kind: "results", mode: searchMode, query: text, ...outcome });
      }
    } catch (error) {
      if (ticket.current === myTicket) {
        const message = error instanceof SearchFailed ? error.message : "Couldn’t reach the server. Try again.";
        setView({ kind: "error", message });
      }
    }
  }

  const copy = COPY[mode];
  const searching = view.kind === "searching";

  return (
    <section>
      <ModeSwitch mode={mode} onChange={setMode} />

      <form onSubmit={onSubmit} className="mt-4 flex flex-col gap-3 sm:flex-row" role="search">
        <label htmlFor="search-input" className="sr-only">
          {copy.label}
        </label>
        <input
          id="search-input"
          name="q"
          type="search"
          required
          maxLength={mode === "ai" ? 1000 : 200}
          placeholder={copy.placeholder}
          className={`${inputClass} flex-1`}
        />
        <button type="submit" disabled={searching} className={primaryButtonClass}>
          {copy.submit}
        </button>
      </form>

      <div className="mt-10" aria-live="polite">
        <SearchOutcome view={view} />
      </div>
    </section>
  );
}

function SearchOutcome({ view }: { view: View }) {
  switch (view.kind) {
    case "idle":
      return null;
    case "searching":
      return (
        <div className="flex items-center gap-3 rounded-2xl border border-line bg-surface px-5 py-4 text-muted">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-accent border-t-transparent" />
          <p className="flex-1">{view.mode === "ai" ? "Finding recipes for you…" : "Searching…"}</p>
          <LiveTimer startedAt={view.startedAt} />
        </div>
      );
    case "error":
      return (
        <p role="alert" className="rounded-2xl bg-danger-soft px-5 py-4 text-danger">
          {view.message}
        </p>
      );
    case "results":
      return <Results view={view} />;
  }
}

function Results({ view }: { view: Extract<View, { kind: "results" }> }) {
  const count = view.recipes.length;
  const summary =
    view.mode === "ai"
      ? `Found in ${formatDuration(view.elapsedMs)}`
      : `${count} result${count === 1 ? "" : "s"} in ${formatDuration(view.elapsedMs)}`;

  return (
    <div>
      <div className="mb-5 flex items-baseline justify-between gap-4">
        <h2 className="font-serif text-2xl font-medium">{view.mode === "ai" ? "Picked for you" : "Matching recipes"}</h2>
        <p className="rounded-full bg-accent-soft px-3 py-1 text-sm text-accent tabular-nums" data-testid="search-elapsed">
          {summary}
        </p>
      </div>
      {count === 0 ? (
        <p className="rounded-2xl border border-line bg-surface px-5 py-4 text-muted">
          No recipes have “{view.query}” in their name or ingredients.
        </p>
      ) : (
        <div className="space-y-4">
          {view.recipes.map((recipe, index) => (
            <RecipeCard key={`${recipe.name}-${index}`} recipe={recipe} />
          ))}
        </div>
      )}
    </div>
  );
}
