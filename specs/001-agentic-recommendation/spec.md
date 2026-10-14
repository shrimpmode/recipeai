# Feature Specification: Goal-Checked Recommendations with Live Progress

**Feature Directory**: `specs/001-agentic-recommendation`
**Created**: 2026-10-13
**Status**: Draft
**Input**: "An agentic workflow: the user sets nutrition goals; when they ask for something (e.g. 'something high fiber'), a multi-step workflow searches the recipes for the request, compares the results to the user's goals, and refines the recommendation when the goals are not met (the order may differ). The user sees, in real time and in plain language, which step is running, instead of just a loading indicator."

<!-- WHAT and WHY only. No languages, frameworks, databases, APIs, or code structure. -->

## User Scenarios

### User Story 1 - Recommendations checked against my goals (Priority: P1)

A user with nutrition goals asks for something ("something high fiber for
lunch"). The system works out the request's nutrition targets first,
searches only among recipes that meet them, and ranks those by how well
they match the request. When too few recipes meet every target, it widens
the search step by step, giving up the user's saved goals before the
nutrients they asked for. The user gets 3 recipes that fit the request and
their targets as well as the corpus allows, and each result says how it
fits.

Today results are only nudged towards goals; nothing checks whether the
final picks actually meet them, so a "high fiber" request can return three
recipes far below the user's fiber target.

**Why this priority**: It is the core value: recommendations the user can
trust against their own targets, not just similar-sounding recipes.

**Independent Test**: With a user whose fiber goal no first-round result
meets, submit "something high fiber"; the returned recipes meet the fiber
goal (or, if the corpus has none that do, the response says so), and each
result states how it compares to the goals.

**Acceptance Scenarios**:

1. **Given** a user with goals and a request whose first-round results all
   meet them, **When** they submit it, **Then** they get 3 recipes after a
   single search round, each with a note on how it fits their goals.
2. **Given** a user with a fiber goal and a request whose most similar
   recipes are low in fiber, **When** they submit it, **Then** the 3 recipes
   returned meet the fiber goal whenever the corpus has 3 that match the
   request and do, even if they are less similar in wording.
3. **Given** a request where no recipe in the corpus meets the targets,
   **When** every widening step is used up, **Then** the user still gets
   the 3 closest recipes, and the result states plainly which target is not
   met.
4. **Given** a user with no goals set and a request naming a nutrient
   ("something high fiber"), **When** they submit it, **Then** the results
   are searched and checked against that nutrient alone.
5. **Given** a user with no goals set and a request naming no nutrient
   ("a quick pasta"), **When** they submit it, **Then** the search is by
   similarity alone and the check is skipped and they get 3 recipes for the request, as
   today.

---

### User Story 2 - See what the assistant is doing while I wait (Priority: P2)

While a recommendation is being prepared, the user sees the current step
in plain language ("Understanding your request", "Searching recipes",
"Widening the search", "Checking against your goals",
"Choosing the best matches"), with the steps already done marked as done.
"Widening the search" appears only when it happens.

**Why this priority**: A request takes several seconds and, with
widening, longer. Showing progress makes the wait feel purposeful and
tells the user the system is working, not stuck.

**Independent Test**: Submit any request and watch the page: at least one
step label appears and changes before the results arrive, and the labels
match what the system actually did ("Widening the search" only when the
search was widened).

**Acceptance Scenarios**:

1. **Given** a submitted request, **When** the system moves to a new step,
   **Then** the page shows that step within about a second, and the
   previous step as done.
2. **Given** a request where too few recipes meet every target, **When**
   the search is widened, **Then** the page shows "Widening the search"
   before the check step.
3. **Given** a request that fails or runs out of time, **When** it ends,
   **Then** the progress is replaced by the existing error message, with no
   technical detail.
4. **Given** a user who relies on a screen reader, **When** the step
   changes, **Then** the new step is announced.

### Edge Cases

- A request unrelated to nutrition or food ("what's the weather"): the user
  gets 3 recipes closest to the request, as today. *Superseded by
  `specs/002-off-topic-requests`: clearly off-topic requests are declined.*
- A request that contradicts a goal ("low carb" with a high carb goal):
  the request's target replaces the goal's for that nutrient.
- Goals that conflict with the request (a 300 kcal/day target and "a hearty
  stew"): the closest recipes are returned and the result says which goal
  is not met.
- A recipe missing a nutrition value for a goal: it counts as not meeting
  that goal, never as meeting it.
- The AI service is slow or down mid-workflow: the existing retry and
  deadline rules apply to the whole request; the user sees the error state,
  never a progress display that stops moving forever.
- The user edits their goals while a request runs: the request uses the
  goals as they were when it started.
- A step finishes faster than the page checks for progress: the page may
  skip showing it, but never shows steps out of order.

## Requirements

### Functional Requirements

- **FR-001**: System MUST resolve each request as a sequence of named
  steps: understand the request, search recipes that meet its targets,
  widen the search (only when needed), check the candidates against the
  targets, and choose and describe the final 3.
- **FR-002**: System MUST derive the request's nutrition targets: every
  goal the user has set, plus any nutrient the request itself names as high
  or low ("high fiber", "low carb"). When both cover the same nutrient, the
  request wins (it is the user's intent for this meal).
- **FR-002a**: System MUST evaluate every candidate recipe against each of
  those targets, using one meal's share of the daily amount (a third, as
  today), and decide per target whether it is met.
- **FR-001a**: The order of steps MUST be fixed by the system, not chosen
  by the AI; the AI only interprets the request and chooses and describes
  the final recipes. Searching, widening and checking MUST be exact
  (rule-based), not judged by the AI.
- **FR-003**: The search MUST consider only recipes that meet every
  target, across the whole corpus, ranked by similarity to the request.
- **FR-004**: When too few recipes meet every target, System MUST widen the
  search in a fixed order, stopping at the first step that finds enough:
  (1) loosen the saved goals' limits; (2) drop the saved goals as limits
  and prefer recipes closest to them instead; (3) drop the request's
  nutrients as limits and prefer recipes that best meet them. Nutrients the
  user asked for are given up last. Widening never discards recipes that
  met more targets in favour of ones that met fewer.
- **FR-005**: Each final recipe MUST come with a short explanation of why
  it fits the request and how it compares to the targets; when a target
  is not met by any returned recipe, the result MUST say which one.
- **FR-006**: When there are no targets (no goals set and no nutrient in
  the request), System MUST search by similarity alone, skip the check, and
  return 3 recipes for the request.
- **FR-007**: While a request is running, System MUST expose its current
  step and the steps completed so far, and the page MUST show them, updated
  within about one second of a change.
- **FR-008**: Step labels shown to the user MUST be plain language from a
  fixed list, with no model names, error text, or internal identifiers.
- **FR-009**: The whole workflow, widening and retries included, MUST
  finish by the request's existing deadline; a request past it ends as an
  error.
- **FR-010**: A request still MUST return exactly 3 recipes on success.

### Access and Data Protection

- **FR-011**: Only the user who submitted a request MAY see its progress and
  results; anyone else is refused, as today.
- **FR-012**: The user's goals and request text are sent to the AI service
  only as needed to resolve the request; they are not written to logs.
- Sensitive data: nutrition goals are personal health-adjacent data. They
  are already stored on the user's profile; this feature adds no new
  storage of them beyond the snapshot a request needs.

### Key Entities

- **Query request** (existing): one AI search and its lifecycle; gains its
  progress (the ordered steps completed and the one running) and, per
  result, the goal comparison.
- **Workflow step**: one named stage of resolving a request, from the fixed
  list in FR-001, with a plain-language label.
- **Nutrition target**: one nutrient the request must satisfy, from the
  user's goals or named in the request: nutrient, direction (at least / at
  most / around), per-meal amount, and source (goal or request).
- **Goal check**: for one recipe, per target: the target, the recipe's
  value, and whether it is met.
- **Widening step**: one loosening of the search's limits from the fixed
  order in FR-004, recorded so the result can say which targets were given
  up.

## Success Criteria

- **SC-001**: For requests where the corpus holds at least 3 recipes that
  match the request and meet its targets, at least 80% of results meet
  every target (measured on a fixed set of sample requests and
  goal profiles).
- **SC-002**: The first progress step is visible within 2 seconds of
  submitting, and the page never goes more than 10 seconds without a
  visible change while a request runs.
- **SC-003**: 95% of requests finish within 15 seconds; no request runs past its deadline (150 seconds today).
- **SC-004**: Every result includes a goal comparison when the request
  has targets; 0 results show technical detail in progress labels or errors.
- **SC-005**: The workflow holds up under the current load (tens of
  concurrent requests) with at most 2 AI calls per request attempt (today:
  1), whether or not the search is widened.

## Assumptions

- Goals stay as they are today: optional daily targets for calories,
  protein, carbs, fat and fiber; one meal is a third of the day.
- "Meets a goal" compares a recipe to the per-meal share: protein and
  fiber are minimums (met at 80% of the share or more); calories, carbs and
  fat are bands (met within ±20% of the share). The thresholds are tunable
  without changing this spec.
- An amount the request states ("at least 30 g protein") is used as given.
  A nutrient named without an amount uses the user's goal for it, else a
  reference daily amount (fiber 28 g, protein 50 g, carbs 275 g, fat 78 g,
  calories 2000): "high" means at least the per-meal share, "low" at most
  half of it.
- Loosening the saved goals (widening step 1) doubles their tolerance:
  minimums met at 60% of the share, bands within ±40%.
- "Enough" recipes for the search means the shortlist the final pick
  chooses from (5 today), so the AI still has a choice.
- The existing submit-then-check flow, retries, and deadline stay; this
  feature changes what happens inside a request and what the page shows
  while waiting.
- Progress is for the live page only; resuming a request's progress after a
  page reload is out of scope (a separate, already planned change).
- Out of scope: chat or follow-up questions, the user editing a request mid
  run, showing every intermediate candidate, keyword search (it stays
  instant and unchanged), and a history of past requests.

## Clarifications

### Session 2026-10-13

- Q: What does the check step compare results against? → A: The user's
  saved goals plus any nutrient the request itself names (FR-002, FR-006,
  US1 scenarios 4–5, Nutrition target entity).
- Q: Who decides the order of steps: fixed code or the AI? → A: A fixed
  workflow; the AI only interprets the request, rewrites the search on
  refinement, and picks and describes; the check is rule-based (FR-001a).
- Q: Should the goals be checked after the similarity search, or used to
  narrow it first? → A: Narrow it first: targets limit the search across
  the whole corpus, similarity ranks within them, and a fixed rule-based
  widening order replaces AI-refined search rounds. This supersedes the
  previous answer's "AI rewrites the search on refinement" (FR-001a,
  FR-003, FR-004, SC-005).
