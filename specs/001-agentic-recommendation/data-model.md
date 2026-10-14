# Data Model: Goal-Checked Recommendations

## QueryRequest (existing table, expanded)

| Field | Type | Rules |
|-------|------|-------|
| `progress` | JSON list of step codes | DB default `[]`; written only while `running` by `report_step()`; cleared by `start()` |
| `unmet_targets` | JSON list of nutrient codes | DB default `[]`; set by `succeed()` |
| `results[].goal_checks` | JSON list inside existing `results` | one entry per target; absent on rows written before this feature (served as `[]`) |

Step codes (fixed order): `understanding`, `searching`, `widening`, `checking`, `choosing`.
Migration `0004`: `AddField` with `db_default`, so processes running the old code can still insert rows (expand only).

## Value objects (pure, `queries/services/targets.py`)

- **Nutrient**: `calories | protein | carbs | fat | fiber`.
- **Direction**: `at_least | at_most | around`.
- **NutrientIntent** (from the interpreter, validated): `nutrient`, `direction ∈ {at_least, at_most}`, `amount: float > 0 | None` (per meal, as stated).
- **NutritionTarget**: `nutrient`, `direction`, `amount` (per meal, > 0), `source ∈ {goal, request}`.
  - Goal: amount = daily goal / 3; direction `at_least` for protein and fiber, `around` for calories, carbs, fat.
  - Request: amount as stated, else (goal or reference daily) / 3 for `at_least`, half that for `at_most`. Reference daily: fiber 28, protein 50, carbs 275, fat 78, calories 2000.
  - Met within tolerance t (strict 0.2, loosened 0.4): at_least `v ≥ a(1−t)`; at_most `v ≤ a(1+t)`; around both. Missing value: never met.
- **GoalCheck**: `nutrient`, `direction`, `target` (amount), `value | null`, `met` (strict).
- **SearchLevel**: `limits: [(target, tolerance)]`, `preferences: [target]`, `widened: bool`. Order: strict → goals loosened → goals as preferences → everything as preferences (levels that would repeat the previous one are skipped).
