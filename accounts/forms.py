from django import forms

from accounts.models import Profile


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = [
            "daily_calorie_target",
            "protein_target_g",
            "carbs_target_g",
            "fat_target_g",
            "fiber_target_g",
        ]
