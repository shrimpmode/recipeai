import type { components } from "./schema";

type Schemas = components["schemas"];

export type Me = Schemas["Me"];
export type Goals = Schemas["Goals"];
export type QueryResult = Schemas["QueryOut"];
export type AiRecipe = Schemas["ResultOut"];
export type KeywordSearchResult = Schemas["SearchOut"];
export type KeywordRecipe = Schemas["RecipeOut"];
export type GoalCheck = Schemas["GoalCheckOut"];
export type Nutrient = Schemas["Nutrient"];
export type SearchStep = Schemas["ProgressEnum"];
