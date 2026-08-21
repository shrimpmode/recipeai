"""Loading and curating rows from the source recipe dataset.

`load_raw_dataset` is the only function that touches the network; everything
else is pure pandas/dict logic so it's cheap to unit test.
"""

import json
import math

import pandas as pd

DATASET_URI = "hf://datasets/datahiveai/recipes-with-nutrition/recipes-with-nutrition.csv"

REQUIRED_COLUMNS = ["recipe_name", "calories", "servings", "total_nutrients"]

# Maps our per-serving Recipe fields to the USDA/Edamam tags used inside the
# source dataset's `total_nutrients` JSON blob.
NUTRIENT_TAG_MAP = {
    "protein_g_per_serving": "PROCNT",
    "fat_g_per_serving": "FAT",
    "carbs_g_per_serving": "CHOCDF",
    "fiber_g_per_serving": "FIBTG",
    "sugar_g_per_serving": "SUGAR",
    "sodium_mg_per_serving": "NA",
}


def load_raw_dataset() -> pd.DataFrame:
    return pd.read_csv(DATASET_URI)


def _parse_json_field(value, default):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def _dish_type_key(value) -> str:
    parsed = _parse_json_field(value, [])
    return parsed[0] if parsed else "unknown"


def select_curated_batch(df: pd.DataFrame, limit: int) -> pd.DataFrame:
    """Pick up to `limit` rows: drop rows missing critical fields, dedupe by
    recipe name, then round-robin across dish types for variety rather than
    taking a naive slice of the dataset.
    """
    clean = df.dropna(subset=REQUIRED_COLUMNS)
    clean = clean[clean["servings"] > 0]
    deduped = clean.drop_duplicates(subset="recipe_name", keep="first").copy()

    if deduped.empty:
        return deduped

    if "dish_type" in deduped.columns:
        deduped["_dish_type_key"] = deduped["dish_type"].apply(_dish_type_key)
    else:
        deduped["_dish_type_key"] = "unknown"
    groups = {key: list(group.index) for key, group in deduped.groupby("_dish_type_key")}
    group_keys = list(groups.keys())
    pointers = {key: 0 for key in group_keys}

    selected_index: list[int] = []
    while len(selected_index) < limit and any(pointers[key] < len(groups[key]) for key in group_keys):
        for key in group_keys:
            if len(selected_index) >= limit:
                break
            position = pointers[key]
            if position < len(groups[key]):
                selected_index.append(groups[key][position])
                pointers[key] = position + 1

    return deduped.loc[selected_index].drop(columns=["_dish_type_key"])


def parse_row_to_recipe_fields(row) -> dict:
    """Parse one source dataset row into kwargs for `Recipe(**fields)`
    (minus `embedding`, which is generated separately)."""
    servings = float(row["servings"])
    if servings <= 0:
        raise ValueError(f"Cannot compute per-serving nutrition for {row.get('recipe_name')!r}: servings={servings}")
    total_nutrients = _parse_json_field(row.get("total_nutrients"), {})
    calories = row.get("calories")

    nutrient_fields = {}
    for field_name, tag in NUTRIENT_TAG_MAP.items():
        entry = total_nutrients.get(tag) if isinstance(total_nutrients, dict) else None
        quantity = entry.get("quantity") if entry else None
        nutrient_fields[field_name] = round(quantity / servings, 2) if quantity is not None else None

    return {
        "recipe_name": row["recipe_name"],
        "source_url": row.get("url") or "",
        "image_url": row.get("image_url") if isinstance(row.get("image_url"), str) else None,
        "servings": servings,
        "calories_per_serving": round(float(calories) / servings, 2) if calories is not None else None,
        "ingredient_lines": _parse_json_field(row.get("ingredient_lines"), []),
        "diet_labels": _parse_json_field(row.get("diet_labels"), []),
        "health_labels": _parse_json_field(row.get("health_labels"), []),
        "cautions": _parse_json_field(row.get("cautions"), []),
        "cuisine_type": _parse_json_field(row.get("cuisine_type"), []),
        "meal_type": _parse_json_field(row.get("meal_type"), []),
        "dish_type": _parse_json_field(row.get("dish_type"), []),
        **nutrient_fields,
    }


def compose_embedding_text(fields: dict) -> str:
    parts = [fields["recipe_name"]]
    parts.extend(fields.get("ingredient_lines") or [])
    parts.extend(fields.get("diet_labels") or [])
    parts.extend(fields.get("health_labels") or [])
    parts.extend(fields.get("meal_type") or [])
    parts.extend(fields.get("dish_type") or [])

    nutrition_bits = []
    labels = (
        ("calories_per_serving", "kcal"),
        ("protein_g_per_serving", "g protein"),
        ("fiber_g_per_serving", "g fiber"),
        ("carbs_g_per_serving", "g carbs"),
        ("fat_g_per_serving", "g fat"),
    )
    for field_name, unit_label in labels:
        value = fields.get(field_name)
        if value is not None:
            nutrition_bits.append(f"{value:.0f} {unit_label}")
    if nutrition_bits:
        parts.append(", ".join(nutrition_bits) + " per serving")

    return ". ".join(str(part) for part in parts if part)
