import type { GoalCheck } from "@/lib/api/types";
import { formatAmount } from "@/lib/format";

export type RecipeCardData = {
  id: number;
  name: string;
  sourceUrl: string;
  imageUrl: string | null;
  description?: string;
  goalChecks?: GoalCheck[];
  calories: number | null;
  protein: number | null;
  carbs: number | null;
  fat: number | null;
  fiber: number | null;
  sugar: number | null;
  sodiumMg: number | null;
};

const MACROS = [
  { key: "protein", label: "Protein", kcalPerGram: 4, color: "bg-protein" },
  { key: "carbs", label: "Carbs", kcalPerGram: 4, color: "bg-carbs" },
  { key: "fat", label: "Fat", kcalPerGram: 9, color: "bg-fat" },
] as const;

/** Share of calories from each macro, as a flat stacked bar. */
function MacroBar({ recipe }: { recipe: RecipeCardData }) {
  const energy = MACROS.map((m) => (recipe[m.key] ?? 0) * m.kcalPerGram);
  const total = energy.reduce((sum, value) => sum + value, 0);
  if (total === 0) return null;
  return (
    <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-sunken" aria-hidden="true">
      {MACROS.map((m, i) => (
        <span key={m.key} className={m.color} style={{ width: `${(energy[i] / total) * 100}%` }} />
      ))}
    </div>
  );
}

const NUTRIENT_LABEL = { calories: "Calories", protein: "Protein", carbs: "Carbs", fat: "Fat", fiber: "Fiber" };
const DIRECTION_SYMBOL = { at_least: "≥", at_most: "≤", around: "≈" };

/** How the recipe compares to each nutrition target, per meal. */
function GoalChecks({ checks }: { checks: GoalCheck[] }) {
  return (
    <ul className="mt-3 flex flex-wrap gap-2 text-xs" aria-label="Your nutrition targets">
      {checks.map((check) => {
        const unit = check.nutrient === "calories" ? " kcal" : " g";
        return (
          <li
            key={check.nutrient}
            className={`rounded-full px-2.5 py-1 tabular-nums ${check.met ? "bg-accent-soft text-accent" : "bg-sunken text-muted"}`}
          >
            <span aria-hidden="true">{check.met ? "✓ " : "✗ "}</span>
            {NUTRIENT_LABEL[check.nutrient]} {formatAmount(check.value, unit)}
            <span className="opacity-70">
              {" "}
              (target {DIRECTION_SYMBOL[check.direction]} {formatAmount(check.target, unit)})
            </span>
            <span className="sr-only">{check.met ? ", met" : ", not met"}</span>
          </li>
        );
      })}
    </ul>
  );
}

export function RecipeCard({ recipe }: { recipe: RecipeCardData }) {
  const facts = [
    { label: "Protein", value: formatAmount(recipe.protein, " g"), dot: "bg-protein" },
    { label: "Carbs", value: formatAmount(recipe.carbs, " g"), dot: "bg-carbs" },
    { label: "Fat", value: formatAmount(recipe.fat, " g"), dot: "bg-fat" },
    { label: "Fiber", value: formatAmount(recipe.fiber, " g"), dot: "bg-fiber" },
    { label: "Sugar", value: formatAmount(recipe.sugar, " g"), dot: "bg-faint" },
    { label: "Sodium", value: formatAmount(recipe.sodiumMg, " mg"), dot: "bg-faint" },
  ];

  return (
    <article className="overflow-hidden rounded-2xl border border-line bg-surface sm:flex" data-testid="recipe-card">
      {recipe.imageUrl && (
        // Source images live on many third-party hosts, so next/image's allow-list doesn't fit here.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={recipe.imageUrl}
          alt=""
          loading="lazy"
          className="h-44 w-full bg-sunken object-cover sm:h-auto sm:w-44 sm:shrink-0"
        />
      )}
      <div className="flex-1 p-5 sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <h3 className="font-serif text-xl font-medium leading-snug">{recipe.name}</h3>
          <p className="shrink-0 text-right">
            <span className="font-serif text-2xl">{formatAmount(recipe.calories)}</span>
            <span className="block text-xs text-faint">kcal / serving</span>
          </p>
        </div>
        {recipe.description && <p className="mt-2 text-sm leading-relaxed text-muted">{recipe.description}</p>}
        {recipe.goalChecks && recipe.goalChecks.length > 0 && <GoalChecks checks={recipe.goalChecks} />}
        <div className="mt-4">
          <MacroBar recipe={recipe} />
        </div>
        <dl className="mt-4 grid grid-cols-3 gap-x-4 gap-y-2 text-sm sm:grid-cols-6">
          {facts.map((fact) => (
            <div key={fact.label}>
              <dt className="flex items-center gap-1.5 text-xs text-faint">
                <span className={`h-1.5 w-1.5 rounded-full ${fact.dot}`} aria-hidden="true" />
                {fact.label}
              </dt>
              <dd className="mt-0.5 font-medium tabular-nums">{fact.value}</dd>
            </div>
          ))}
        </dl>
        {recipe.sourceUrl && (
          <a
            href={recipe.sourceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-5 inline-block text-sm font-medium text-accent hover:text-accent-hover"
          >
            View full recipe →
          </a>
        )}
      </div>
    </article>
  );
}
