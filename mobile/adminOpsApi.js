/**
 * Admin Ops Dashboard API helpers (internal).
 * Lightweight wrapper around /admin/ops-dashboard and safe operator actions.
 */

const API_BASE =
  process.env.EXPO_PUBLIC_API_BASE?.trim() ||
  "https://kcal-scan-production.up.railway.app";

function devLog(...args) {
  if (typeof __DEV__ !== "undefined" && __DEV__) {
    // eslint-disable-next-line no-console
    console.log("[AdminOpsApi]", ...args);
  }
}

async function safeJson(res) {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

export async function fetchOpsDashboard(params = {}) {
  const p = params && typeof params === "object" ? params : {};
  const limitTargets = Number.isFinite(Number(p.limit_targets)) ? Number(p.limit_targets) : 20;
  const limitAreas = Number.isFinite(Number(p.limit_areas)) ? Number(p.limit_areas) : 5;
  const scanWindowDays = Number.isFinite(Number(p.scan_window_days)) ? Number(p.scan_window_days) : 7;
  const url =
    `${API_BASE}/admin/ops-dashboard?` +
    `limit_targets=${encodeURIComponent(limitTargets)}` +
    `&limit_areas=${encodeURIComponent(limitAreas)}` +
    `&scan_window_days=${encodeURIComponent(scanWindowDays)}`;
  try {
    const res = await fetch(url, { method: "GET", headers: { accept: "application/json" } });
    if (!res.ok) {
      devLog("non-200", res.status);
      return { ok: false, error: `http_${res.status}` };
    }
    const data = await safeJson(res);
    return { ok: true, data };
  } catch (e) {
    devLog("network error", String(e?.message || e));
    return { ok: false, error: "network_error" };
  }
}

async function postJson(path, body) {
  const url = `${API_BASE}${path}`;
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { accept: "application/json", "content-type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const data = await safeJson(res);
    if (!res.ok) {
      return { ok: false, error: `http_${res.status}`, data };
    }
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: "network_error" };
  }
}

export function applyNextTargets({ limit = 20, area_keys = null } = {}) {
  return postJson("/admin/ops-dashboard/apply-next-targets", { limit, area_keys });
}

export function runBatchDryRun({ limit_users = 100 } = {}) {
  return postJson("/admin/ops-dashboard/run-batch-dry-run", { limit_users });
}

export function checkReceipts({ limit = 100 } = {}) {
  return postJson("/admin/ops-dashboard/check-receipts", { limit });
}

export function runAutoPromote({ limit = 100, area_key = "" } = {}) {
  return postJson("/admin/ops-dashboard/run-auto-promote", { limit, area_key });
}

