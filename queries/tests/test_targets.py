"""Nutrition targets: merging goals with the request, the met rule, and the widening order."""

from django.test import SimpleTestCase

from queries.services.targets import (
    LOOSE,
    STRICT,
    Direction,
    Nutrient,
    NutrientIntent,
    NutritionTarget,
    Source,
    is_met,
    merge_targets,
    rank_key,
    widening_levels,
)


def target(nutrient: Nutrient, direction: Direction, amount: float, source: Source = Source.GOAL) -> NutritionTarget:
    return NutritionTarget(nutrient, direction, amount, source)


class MergeTargetsTests(SimpleTestCase):
    def test_goals_become_per_meal_targets_with_their_direction(self):
        targets = merge_targets({Nutrient.FIBER: 30, Nutrient.CALORIES: 1800}, [])

        self.assertCountEqual(
            targets,
            [target(Nutrient.FIBER, Direction.AT_LEAST, 10), target(Nutrient.CALORIES, Direction.AROUND, 600)],
        )

    def test_the_request_replaces_the_goal_for_the_same_nutrient(self):
        targets = merge_targets({Nutrient.CARBS: 300}, [NutrientIntent(nutrient=Nutrient.CARBS, direction="at_most")])

        # "low" is at most half the per-meal share of the user's own goal.
        self.assertEqual(targets, (target(Nutrient.CARBS, Direction.AT_MOST, 50, Source.REQUEST),))

    def test_a_stated_amount_is_used_as_given_and_reference_amounts_fill_the_rest(self):
        targets = merge_targets(
            {},
            [
                NutrientIntent(nutrient=Nutrient.PROTEIN, direction="at_least", amount=30),
                NutrientIntent(nutrient=Nutrient.FIBER, direction="at_least"),
            ],
        )

        self.assertCountEqual(
            targets,
            [
                target(Nutrient.PROTEIN, Direction.AT_LEAST, 30, Source.REQUEST),
                target(Nutrient.FIBER, Direction.AT_LEAST, 28 / 3, Source.REQUEST),
            ],
        )

    def test_unset_or_zero_goals_are_not_targets(self):
        self.assertEqual(merge_targets({Nutrient.FAT: 0}, []), ())


class IsMetTests(SimpleTestCase):
    def test_minimums_bands_and_maximums_at_strict_and_loose_tolerance(self):
        minimum = target(Nutrient.FIBER, Direction.AT_LEAST, 10)
        band = target(Nutrient.CALORIES, Direction.AROUND, 600)
        maximum = target(Nutrient.CARBS, Direction.AT_MOST, 50)

        self.assertTrue(is_met(minimum, 8, STRICT))
        self.assertFalse(is_met(minimum, 7.9, STRICT))
        self.assertTrue(is_met(minimum, 6, LOOSE))
        self.assertTrue(is_met(band, 720, STRICT))
        self.assertFalse(is_met(band, 721, STRICT))
        self.assertFalse(is_met(band, 479, STRICT))
        self.assertTrue(is_met(maximum, 60, STRICT))
        self.assertFalse(is_met(maximum, 61, STRICT))

    def test_a_missing_value_never_meets_a_target(self):
        self.assertFalse(is_met(target(Nutrient.CARBS, Direction.AT_MOST, 50), None, LOOSE))


class RankKeyTests(SimpleTestCase):
    def test_recipes_meeting_the_same_targets_tie_so_similarity_order_stands(self):
        band = target(Nutrient.CALORIES, Direction.AROUND, 600)

        self.assertEqual(rank_key({Nutrient.CALORIES: 610}, [band]), rank_key({Nutrient.CALORIES: 700}, [band]))
        self.assertLess(rank_key({Nutrient.CALORIES: 700}, [band]), rank_key({Nutrient.CALORIES: 800}, [band]))
        self.assertLess(rank_key({Nutrient.CALORIES: 800}, [band]), rank_key({Nutrient.CALORIES: 900}, [band]))

    def test_a_nutrient_the_user_asked_for_outranks_any_number_of_saved_goals(self):
        protein = target(Nutrient.PROTEIN, Direction.AT_LEAST, 80, Source.REQUEST)
        calories = target(Nutrient.CALORIES, Direction.AROUND, 600)
        fat = target(Nutrient.FAT, Direction.AROUND, 20)
        targets = [protein, calories, fat]
        meets_the_request = {Nutrient.PROTEIN: 85, Nutrient.CALORIES: 900, Nutrient.FAT: 40}
        meets_both_goals = {Nutrient.PROTEIN: 30, Nutrient.CALORIES: 600, Nutrient.FAT: 20}

        self.assertLess(rank_key(meets_the_request, targets), rank_key(meets_both_goals, targets))


class WideningLevelsTests(SimpleTestCase):
    def test_goals_are_loosened_then_dropped_before_the_request_is(self):
        goal = target(Nutrient.CALORIES, Direction.AROUND, 600)
        asked = target(Nutrient.FIBER, Direction.AT_LEAST, 10, Source.REQUEST)

        levels = widening_levels((goal, asked))

        self.assertEqual(
            [level.limits for level in levels],
            [((goal, STRICT), (asked, STRICT)), ((goal, LOOSE), (asked, STRICT)), ((asked, STRICT),), ()],
        )
        self.assertEqual([level.widened for level in levels], [False, True, True, True])

    def test_without_targets_there_is_one_unfiltered_level(self):
        (level,) = widening_levels(())

        self.assertEqual((level.limits, level.widened), ((), False))

    def test_request_only_targets_go_straight_from_strict_to_unfiltered(self):
        asked = target(Nutrient.FIBER, Direction.AT_LEAST, 10, Source.REQUEST)

        self.assertEqual([level.limits for level in widening_levels((asked,))], [((asked, STRICT),), ()])
