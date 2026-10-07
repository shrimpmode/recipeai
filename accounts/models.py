from django.conf import settings
from django.db import models


class Profile(models.Model):
    """A user's optional nutrition goal targets.

    Every goal field is optional: a user may submit queries before deciding
    on any targets, in which case retrieval falls back to prompt-only
    similarity (see queries.services.retrieval).
    """

    # Declared for Pyright, which can't see Django's implicit fields (mypy's plugin can).
    id: int
    user_id: int

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")

    daily_calorie_target = models.FloatField(null=True, blank=True)
    protein_target_g = models.FloatField(null=True, blank=True)
    carbs_target_g = models.FloatField(null=True, blank=True)
    fat_target_g = models.FloatField(null=True, blank=True)
    fiber_target_g = models.FloatField(null=True, blank=True)

    def __str__(self) -> str:
        return f"Profile({self.user})"

    def has_goals(self) -> bool:
        return any(
            value is not None
            for value in (
                self.daily_calorie_target,
                self.protein_target_g,
                self.carbs_target_g,
                self.fat_target_g,
                self.fiber_target_g,
            )
        )
