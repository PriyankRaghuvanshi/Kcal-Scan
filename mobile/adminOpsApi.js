/**
 * Admin Ops Dashboard API helpers (internal).
 * Lightweight wrapper around /admin/ops-dashboard and safe operator actions.
 */
import { safeGetOpsDashboardSummary, safeObject } from "./startupSafety";
import AsyncStorage from "@react-native-async-storage/async-storage";

const API_BASE =
  process.env.EXPO_PUBLIC_API_BASE?.trim() ||
  "https://kcal-scan-production.up.railway.app";
const ADMIN_AUTH_STORAGE_KEY = "kcal_admin_auth_v1";
let adminAuthToken = "";
let adminAuthUsername = "";

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

async function ensureAdminAuthLoaded() {
  if (adminAuthToken) return;
  try {
    const raw = await AsyncStorage.getItem(ADMIN_AUTH_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    adminAuthToken = String(parsed?.token || "");
    adminAuthUsername = String(parsed?.username || "");
  } catch {}
}

async function saveAdminAuthState({ token = "", username = "" } = {}) {
  adminAuthToken = String(token || "");
  adminAuthUsername = String(username || "");
  try {
    await AsyncStorage.setItem(
      ADMIN_AUTH_STORAGE_KEY,
      JSON.stringify({ token: adminAuthToken, username: adminAuthUsername })
    );
  } catch {}
}

export async function clearAdminAuthState() {
  adminAuthToken = "";
  adminAuthUsername = "";
  try {
    await AsyncStorage.removeItem(ADMIN_AUTH_STORAGE_KEY);
  } catch {}
}

function adminHeaders(extra = {}) {
  const h = { accept: "application/json", ...extra };
  if (adminAuthToken) h.Authorization = `Bearer ${adminAuthToken}`;
  return h;
}

export async function fetchOpsDashboard(params = {}) {
  await ensureAdminAuthLoaded();
  const p = params && typeof params === "object" ? params : {};
  const limitTargets = Number.isFinite(Number(p.limit_targets)) ? Number(p.limit_targets) : 20;
  const limitAreas = Number.isFinite(Number(p.limit_areas)) ? Number(p.limit_areas) : 5;
  const scanWindowDays = Number.isFinite(Number(p.scan_window_days)) ? Number(p.scan_window_days) : 7;
  const goalCoachWindowDays = Number.isFinite(Number(p.goal_coach_window_days)) ? Number(p.goal_coach_window_days) : 7;
  const url =
    `${API_BASE}/admin/ops-dashboard?` +
    `limit_targets=${encodeURIComponent(limitTargets)}` +
    `&limit_areas=${encodeURIComponent(limitAreas)}` +
    `&scan_window_days=${encodeURIComponent(scanWindowDays)}` +
    `&goal_coach_window_days=${encodeURIComponent(goalCoachWindowDays)}`;
  try {
    const res = await fetch(url, { method: "GET", headers: adminHeaders() });
    if (!res.ok) {
      devLog("non-200", res.status);
      return { ok: false, error: `http_${res.status}` };
    }
    const data = await safeJson(res);
    return { ok: true, data: safeGetOpsDashboardSummary(data) };
  } catch (e) {
    devLog("network error", String(e?.message || e));
    return { ok: false, error: "network_error" };
  }
}

async function postJson(path, body) {
  await ensureAdminAuthLoaded();
  const url = `${API_BASE}${path}`;
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: adminHeaders({ "content-type": "application/json" }),
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

export async function adminLogin({ username = "", password = "" } = {}) {
  const u = String(username || "").trim();
  const p = String(password || "");
  if (!u || !p) return { ok: false, error: "missing_credentials" };
  try {
    const res = await fetch(`${API_BASE}/admin/auth/login`, {
      method: "POST",
      headers: { accept: "application/json", "content-type": "application/json" },
      body: JSON.stringify({ username: u, password: p }),
    });
    const data = await safeJson(res);
    if (!res.ok) {
      const detail = safeObject(data?.detail, {});
      return {
        ok: false,
        error: `http_${res.status}`,
        data,
        code: String(detail?.error || ""),
        retry_after_sec: Number.isFinite(Number(detail?.retry_after_sec)) ? Number(detail.retry_after_sec) : null,
      };
    }
    const token = String(data?.token || "");
    if (!token) return { ok: false, error: "missing_token" };
    await saveAdminAuthState({ token, username: String(data?.username || u) });
    return { ok: true, data: safeOpsActionResult(data) };
  } catch {
    return { ok: false, error: "network_error" };
  }
}

export async function adminAuthMe() {
  await ensureAdminAuthLoaded();
  if (!adminAuthToken) return { ok: false, error: "not_logged_in" };
  try {
    const res = await fetch(`${API_BASE}/admin/auth/me`, { method: "GET", headers: adminHeaders() });
    const data = await safeJson(res);
    if (!res.ok) return { ok: false, error: `http_${res.status}`, data };
    return { ok: true, data: safeOpsActionResult(data) };
  } catch {
    return { ok: false, error: "network_error" };
  }
}

export async function getAdminAuthSnapshot() {
  await ensureAdminAuthLoaded();
  return { hasToken: Boolean(adminAuthToken), username: adminAuthUsername || "" };
}

export function safeOpsActionResult(raw) {
  return safeObject(raw, {});
}

export function applyNextTargets({ limit = 20, area_keys = null } = {}) {
  return postJson("/admin/ops-dashboard/apply-next-targets", { limit, area_keys }).then((res) =>
    res?.ok ? { ...res, data: safeOpsActionResult(res.data) } : res
  );
}

export function runBatchDryRun({ limit_users = 100 } = {}) {
  return postJson("/admin/ops-dashboard/run-batch-dry-run", { limit_users }).then((res) =>
    res?.ok ? { ...res, data: safeOpsActionResult(res.data) } : res
  );
}

export function checkReceipts({ limit = 100 } = {}) {
  return postJson("/admin/ops-dashboard/check-receipts", { limit }).then((res) =>
    res?.ok ? { ...res, data: safeOpsActionResult(res.data) } : res
  );
}

export function runAutoPromote({ limit = 100, area_key = "" } = {}) {
  return postJson("/admin/ops-dashboard/run-auto-promote", { limit, area_key }).then((res) =>
    res?.ok ? { ...res, data: safeOpsActionResult(res.data) } : res
  );
}

export async function fetchCoachNudgeDebugUser({ user_id = "", day = "" } = {}) {
  const uid = String(user_id || "").trim();
  if (!uid) return { ok: false, error: "user_id_required" };
  const params = [`user_id=${encodeURIComponent(uid)}`];
  const dayIso = String(day || "").trim();
  if (dayIso) params.push(`day=${encodeURIComponent(dayIso)}`);
  const url = `${API_BASE}/push/send-coach-nudges/debug-user?${params.join("&")}`;
  try {
    const res = await fetch(url, { method: "GET", headers: { accept: "application/json" } });
    const data = await safeJson(res);
    if (!res.ok) return { ok: false, error: `http_${res.status}`, data };
    return { ok: true, data: safeOpsActionResult(data) };
  } catch {
    return { ok: false, error: "network_error" };
  }
}

export function runCoachNudgeDryRunForUser({ user_id = "", day = "", local_hour = null } = {}) {
  const uid = String(user_id || "").trim();
  if (!uid) return Promise.resolve({ ok: false, error: "user_id_required" });
  const payload = { user_id: uid, dry_run: true };
  const dayIso = String(day || "").trim();
  if (dayIso) payload.day = dayIso;
  if (Number.isFinite(Number(local_hour))) payload.local_hour = Number(local_hour);
  return postJson("/push/send-coach-nudges", payload).then((res) =>
    res?.ok ? { ...res, data: safeOpsActionResult(res.data) } : res
  );
}

export function runCoachNudgeRealSendForUser({ user_id = "", day = "", local_hour = null } = {}) {
  const uid = String(user_id || "").trim();
  if (!uid) return Promise.resolve({ ok: false, error: "user_id_required" });
  const payload = { user_id: uid, dry_run: false };
  const dayIso = String(day || "").trim();
  if (dayIso) payload.day = dayIso;
  if (Number.isFinite(Number(local_hour))) payload.local_hour = Number(local_hour);
  return postJson("/push/send-coach-nudges", payload).then((res) =>
    res?.ok ? { ...res, data: safeOpsActionResult(res.data) } : res
  );
}

export async function fetchCoachNudgeJobHealth() {
  await ensureAdminAuthLoaded();
  try {
    const res = await fetch(`${API_BASE}/admin/jobs/coach-nudges/health`, {
      method: "GET",
      headers: adminHeaders(),
    });
    const data = await safeJson(res);
    if (!res.ok) return { ok: false, error: `http_${res.status}`, data };
    return { ok: true, data: safeOpsActionResult(data) };
  } catch {
    return { ok: false, error: "network_error" };
  }
}
