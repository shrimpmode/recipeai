"""Nutrition targets: what a request's recipes must meet, and how strictly. Pure, no I/O.

A target comes from the user's daily goals or from a nutrient the request names
("high fiber"); the request wins for a nutrient both cover. Amounts are per
meal: a third of the daily figure. The search narrows by targets first and, when
too few recipes meet them, widens in the fixed order of `widening_levels`:
the saved goals are loosened, then given up as limits, before the nutrients the
user asked for.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

MEALS_PER_DAY = 3
STRICT = 0.2
LOOSE = 0.4  # widening step a: twice the strict tolerance


class Nutrient(StrEnum):
    CALORIES = "calories"
    PROTEIN = "protein"
    CARBS = "carbs"
    FAT = "fat"
    FIBER = "fiber"


class Direction(StrEnum):
    AT_LEAST = "at_least"
    AT_MOST = "at_most"
    AROUND = "around"


class Source(StrEnum):
    GOAL = "goal"
    REQUEST = "request"


RECIPE_FIELD = {
    Nutrient.CALORIES: "calories_per_serving",
    Nutrient.PROTEIN: "protein_g_per_serving",
    Nutrient.CARBS: "carbs_g_per_serving",
    Nutrient.FAT: "fat_g_per_serving",
    Nutrient.FIBER: "fiber_g_per_serving",
}
GOAL_FIELD = {
    Nutrient.CALORIES: "daily_calorie_target",
    Nutrient.PROTEIN: "protein_target_g",
    Nutrient.CARBS: "carbs_target_g",
    Nutrient.FAT: "fat_target_g",
    Nutrient.FIBER: "fiber_target_g",
}
# Protein and fiber are worth reaching; overshooting calories, carbs or fat is a miss too.
_GOAL_DIRECTION = {
    Nutrient.CALORIES: Direction.AROUND,
    Nutrient.PROTEIN: Direction.AT_LEAST,
    Nutrient.CARBS: Direction.AROUND,
    Nutrient.FAT: Direction.AROUND,
    Nutrient.FIBER: Direction.AT_LEAST,
}
# Standard daily values, for a nutrient the request names when the user has no goal for it.
_REFERENCE_DAILY = {
    Nutrient.CALORIES: 2000.0,
    Nutrient.PROTEIN: 50.0,
    Nutrient.CARBS: 275.0,
    Nutrient.FAT: 78.0,
    Nutrient.FIBER: 28.0,
}


class NutrientIntent(BaseModel, frozen=True):
    """A nutrient the request asks for, as the interpreter read it (validated: it comes from a model)."""

    nutrient: Nutrient
    direction: Literal["at_least", "at_most"]
    amount: float | None = Field(default=None, gt=0, description="Per-meal amount, only if the request states one")


@dataclass(frozen=True)
class NutritionTarget:
    nutrient: Nutrient
    direction: Direction
    amount: float  # per meal, > 0
    source: Source


@dataclass(frozen=True)
class GoalCheck:
    nutrient: Nutrient
    direction: Direction
    target: float
    value: float | None
    met: bool


@dataclass(frozen=True)
class SearchLevel:
    """One search: the corpus filtered by `limits` (each target with its tolerance).
    Every target still ranks the results (`rank_key`), limit or not."""

    limits: tuple[tuple[NutritionTarget, float], ...]
    widened: bool


def merge_targets(
    daily_goals: Mapping[Nutrient, float | None], intents: Sequence[NutrientIntent]
) -> tuple[NutritionTarget, ...]:
    by_nutrient: dict[Nutrient, NutritionTarget] = {}
    for nutrient, daily in daily_goals.items():
        if daily:  # unset or zero isn't a goal
            by_nutrient[nutrient] = NutritionTarget(
                nutrient, _GOAL_DIRECTION[nutrient], daily / MEALS_PER_DAY, Source.GOAL
            )
    for intent in intents:
        direction = Direction(intent.direction)
        amount = intent.amount
        if amount is None:
            share = (daily_goals.get(intent.nutrient) or _REFERENCE_DAILY[intent.nutrient]) / MEALS_PER_DAY
            amount = share if direction is Direction.AT_LEAST else share / 2
        by_nutrient[intent.nutrient] = NutritionTarget(intent.nutrient, direction, amount, Source.REQUEST)
    return tuple(by_nutrient.values())


def bounds(target: NutritionTarget, tolerance: float) -> tuple[float | None, float | None]:
    """The (low, high) a recipe's value must fall within; None is unbounded."""
    low = target.amount * (1 - tolerance) if target.direction is not Direction.AT_MOST else None
    high = target.amount * (1 + tolerance) if target.direction is not Direction.AT_LEAST else None
    return low, high


def is_met(target: NutritionTarget, value: float | None, tolerance: float) -> bool:
    if value is None:
        return False
    low, high = bounds(target, tolerance)
    return (low is None or value >= low) and (high is None or value <= high)


def check(values: Mapping[Nutrient, float | None], targets: Sequence[NutritionTarget]) -> tuple[GoalCheck, ...]:
    return tuple(
        GoalCheck(t.nutrient, t.direction, t.amount, values.get(t.nutrient), is_met(t, values.get(t.nutrient), STRICT))
        for t in targets
    )


def rank_key(values: Mapping[Nutrient, float | None], targets: Sequence[NutritionTarget]) -> tuple[int, float]:
    """Sort key, lower first: more targets met, then a smaller shortfall from the unmet ones.
    Recipes meeting the same targets tie, so a stable sort keeps their similarity order."""
    unmet = [t for t in targets if not is_met(t, values.get(t.nutrient), STRICT)]
    return -(len(targets) - len(unmet)), sum(_shortfall(t, values.get(t.nutrient)) for t in unmet)


def widening_levels(targets: Sequence[NutritionTarget]) -> tuple[SearchLevel, ...]:
    """Strict first; then (a) goals loosened, (b) goals no longer limits, (c) no limits at all.
    The last level never filters, so the search always ends with the best the corpus has."""
    goals = tuple(t for t in targets if t.source is Source.GOAL)
    asked = tuple(t for t in targets if t.source is Source.REQUEST)
    if not targets:
        return (SearchLevel((), widened=False),)
    levels = [SearchLevel(tuple((t, STRICT) for t in (*goals, *asked)), widened=False)]
    if goals:
        levels.append(SearchLevel((*((t, LOOSE) for t in goals), *((t, STRICT) for t in asked)), widened=True))
        levels.append(SearchLevel(tuple((t, STRICT) for t in asked), widened=True))
    if asked:
        levels.append(SearchLevel((), widened=True))
    return tuple(levels)


def _shortfall(target: NutritionTarget, value: float | None) -> float:
    """How far a value misses the target, relative to it; a missing value misses entirely."""
    if value is None:
        return 1.0
    if target.direction is Direction.AT_LEAST:
        miss = max(0.0, target.amount - value)
    elif target.direction is Direction.AT_MOST:
        miss = max(0.0, value - target.amount)
    else:
        miss = abs(value - target.amount)
    return miss / target.amount
