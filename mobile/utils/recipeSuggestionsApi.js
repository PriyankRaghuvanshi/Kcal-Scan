// Post-scan recipe suggestions (Spoonacular + personalization on server).

const API_BASE =
  process.env.EXPO_PUBLIC_API_BASE?.trim() || "https://kcal-scan-production.up.railway.app";

function normalizeDietStyle(raw) {
  const s = String(raw || "non_veg").trim().toLowerCase();
  if (!s) return "non-veg";
  return s.replace(/_/g, "-");
}

export async function fetchRecipeSuggestions({ userId, meal, dietStyle, goalType, analysisId, plan }) {
  if (!userId || !meal) return null;
  try {
    const res = await fetch(`${API_BASE}/recipes/suggest`, {
      method: "POST",
      headers: {
        accept: "application/json",
        "Content-Type": "application/json",
        "X-User-Id": userId,
      },
      body: JSON.stringify({
        user_id: userId,
        analysis_id: String(analysisId || ""),
        meal,
        diet_style: normalizeDietStyle(dietStyle),
        goal_type: String(goalType || "fat_loss"),
        plan: String(plan || "free").toLowerCase(),
      }),
    });
    if (!res.ok) return null;
    const data = await res.json().catch(() => null);
    return data;
  } catch {
    return null;
  }
}

export async function fetchSavedRecipes(userId) {
  if (!userId) return null;
  try {
    const res = await fetch(
      `${API_BASE}/recipes/saved?user_id=${encodeURIComponent(userId)}`,
      {
        headers: {
          accept: "application/json",
          "X-User-Id": userId,
        },
      }
    );
    if (!res.ok) return null;
    return await res.json().catch(() => null);
  } catch {
    return null;
  }
}

export function postRecipeFeedback({ userId, recipeKey, action, cuisine, mealTag, recipeSnapshot }) {
  if (!userId || !recipeKey || !action) return;
  const body = {
    user_id: userId,
    recipe_key: recipeKey,
    action,
    cuisine: String(cuisine || ""),
    meal_tag: String(mealTag || ""),
    recipe_snapshot: recipeSnapshot && typeof recipeSnapshot === "object" ? recipeSnapshot : {},
  };
  void fetch(`${API_BASE}/recipes/feedback`, {
    method: "POST",
    headers: {
      accept: "application/json",
      "Content-Type": "application/json",
      "X-User-Id": userId,
    },
    body: JSON.stringify(body),
  }).catch(() => {});
}
