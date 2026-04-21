const API_BASE =
  process.env.EXPO_PUBLIC_API_BASE?.trim() ||
  "https://kcal-scan-production.up.railway.app";

function normalizeNumber(value) {
  const n = Number(value);
  return Number.isFinite(n) ? Math.round(n * 10) / 10 : 0;
}

function normalizeItems(items) {
  return (Array.isArray(items) ? items : [])
    .map((item) => {
      const itemName = String(item?.item_name || item?.name || item?.item || "").trim();
      if (!itemName) return null;
      return {
        item_name: itemName,
        estimated_calories: normalizeNumber(item?.estimated_calories ?? item?.kcal),
        estimated_protein_g: normalizeNumber(item?.estimated_protein_g ?? item?.protein_g),
        estimated_carbs_g: normalizeNumber(item?.estimated_carbs_g ?? item?.carbs_g),
        estimated_fat_g: normalizeNumber(item?.estimated_fat_g ?? item?.fat_g),
      };
    })
    .filter(Boolean);
}

async function safeJson(res) {
  const text = await res.text();
  if (!text) {
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return {};
  }
  let parsed = null;
  try {
    parsed = JSON.parse(text);
  } catch {
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${text.slice(0, 220)}`);
    throw new Error(text.slice(0, 220) || "Invalid response");
  }
  if (!res.ok) {
    const detail = parsed?.detail;
    const message =
      parsed?.error ||
      parsed?.message ||
      (typeof detail === "string" ? detail : detail?.error || detail?.message) ||
      `HTTP ${res.status}`;
    throw new Error(String(message || `HTTP ${res.status}`));
  }
  return parsed;
}

export async function contributeScanData({ userId, placeName, placeId, items, totalKcal, source }) {
  const payload = {
    user_id: String(userId || "").trim(),
    place_name: String(placeName || "").trim() || null,
    place_id: String(placeId || "").trim() || null,
    items: normalizeItems(items),
    total_kcal: normalizeNumber(totalKcal),
    source: String(source || "meal_photo_scan").trim() || "meal_photo_scan",
  };

  if (!payload.user_id) {
    throw new Error("Missing user id.");
  }
  if (!payload.items.length) {
    throw new Error("No scan items to contribute.");
  }

  const res = await fetch(`${API_BASE}/scan/contribute`, {
    method: "POST",
    headers: {
      accept: "application/json",
      "content-type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return await safeJson(res);
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    contributeScanData,
  };
}
