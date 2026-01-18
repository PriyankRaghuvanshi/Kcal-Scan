// mobile/src/lib/scans.js
import { supabase } from "./supabase";

// Calls Postgres function consume_scan(user_id, source)
export async function consumeScan({ userId, source }) {
  if (!supabase) throw new Error("Supabase not configured");
  if (!userId) throw new Error("Missing userId");

  const { data, error } = await supabase.rpc("consume_scan", {
    p_user_id: userId,
    p_source: source || "photo",
  });

  if (error) {
    // This error usually includes "limit reached"
    throw new Error(error.message || "Scan limit check failed");
  }
  return data; // { allowed, plan, remaining_day, remaining_month, used_day, used_month }
}

export async function upsertEntitlement({ userId, entitlement }) {
  if (!supabase) throw new Error("Supabase not configured");
  if (!userId) throw new Error("Missing userId");

  const { error } = await supabase
    .from("user_entitlements")
    .upsert(
      { user_id: userId, entitlement: entitlement || "free" },
      { onConflict: "user_id" }
    );

  if (error) throw new Error(error.message || "Failed to save entitlement");
}

