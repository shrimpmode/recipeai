from django.contrib import admin

from recipes.models import Recipe


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ("recipe_name", "calories_per_serving", "protein_g_per_serving", "fiber_g_per_serving")
    search_fields = ("recipe_name",)
