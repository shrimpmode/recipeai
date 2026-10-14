# Feature Specification: Decline Off-Topic Requests

**Feature Directory**: `specs/002-off-topic-requests`
**Created**: 2026-10-14
**Status**: Approved
**Input**: "Validate that a request is related to nutrition and recipes, as part of the AI search workflow."

<!-- WHAT and WHY only. -->

## User Scenarios

### User Story 1 - A clearly off-topic request gets a polite answer, not recipes (Priority: P1)

A signed-in user types something unrelated to food ("write me a poem about
the sea"). Instead of three recipes that answer nothing, they see a short,
friendly message saying the assistant helps with meals and recipes, with an
example of what to ask. It is not shown as an error, and nothing is retried.

**Why this priority**: Recipes for an unrelated request mislead the user and
pay for AI work that answers nothing.

**Independent Test**: Submit "write me a poem about the sea"; the page shows
the message after the first step and no recipe cards. Submit "I'm starving";
3 recipes appear as before.

**Acceptance Scenarios**:

1. **Given** a clearly off-topic request, **When** it is submitted, **Then**
   the page shows "Understanding your request", then the friendly message,
   and no recipes.
2. **Given** a vague but food-related request ("something light", "I'm
   starving"), **When** it is submitted, **Then** it is treated as on topic
   and returns 3 recipes.
3. **Given** a request the system cannot classify, **When** it is
   submitted, **Then** it is treated as on topic.

### Edge Cases

- Mixed requests ("I'm sad, cook me something comforting"): on topic.
- A request about nutrition without a dish ("how much fiber should I eat?"):
  on topic; it gets recipes that fit, as today.
- The AI service fails while classifying: the existing retries and deadline
  apply, as for any request.

## Requirements

### Functional Requirements

- **FR-001**: System MUST decide whether each AI search request is about
  food, meals, recipes or nutrition, while it interprets the request.
- **FR-002**: The decision MUST be lenient: only clearly unrelated requests
  are off topic; when unsure, the request is on topic.
- **FR-003**: An off-topic request MUST end after the understanding step,
  with no recipe search and no further AI work.
- **FR-004**: The user MUST see a plain message with an example request,
  not an error and not recipes; the request is not retried.
- **FR-005**: When the classification is missing from the AI's answer, the
  request MUST be treated as on topic.
- **FR-006**: Only the user who submitted a request MAY see its outcome, as
  today.

### Key Entities

- **Query request** (existing): gains whether it was declined as off topic.

## Success Criteria

- **SC-001**: On-topic requests make no more AI calls than before (2 per
  attempt).
- **SC-002**: An off-topic request costs 1 AI call per attempt.
- **SC-003**: On a fixed sample set, at least 90% of clearly off-topic
  requests are declined and at most 2% of food requests are wrongly
  declined.

## Assumptions

- This is not a security boundary: prompt injection is contained by the
  validated AI output and the shortlist-only picks; abuse cost by a rate
  limit (a separate follow-up).
- No new progress step: the decision happens inside "Understanding your
  request".
- Supersedes the off-topic edge case of `specs/001-agentic-recommendation`
  ("3 closest recipes, as today").

## Clarifications

### Session 2026-10-14

- Nothing material left open: the approach (decide inside the existing
  interpreter call, lenient, fail open, not an error) was agreed before
  this spec was written.
