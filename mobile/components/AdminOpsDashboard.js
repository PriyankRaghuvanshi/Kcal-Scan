import React, { useEffect, useMemo, useState } from "react";
import { View, Text, TouchableOpacity, ScrollView, ActivityIndicator, StyleSheet, TextInput, Alert } from "react-native";
import {
  fetchOpsDashboard,
  applyNextTargets,
  runBatchDryRun,
  checkReceipts,
  runAutoPromote,
  fetchCoachNudgeDebugUser,
  runCoachNudgeDryRunForUser,
  runCoachNudgeRealSendForUser,
  fetchCoachNudgeJobHealth,
  adminLogin,
  adminAuthMe,
  getAdminAuthSnapshot,
  clearAdminAuthState,
} from "../adminOpsApi";
import { safeArray, safeObject } from "../startupSafety";

function num(x, d = 0) {
  const n = Number(x);
  return Number.isFinite(n) ? n : d;
}

function pct(x) {
  const n = Number(x);
  if (!Number.isFinite(n)) return "-";
  return `${Math.round(n)}%`;
}

function goalCoachActionLabel(actionType) {
  const t = String(actionType || "").trim().toLowerCase();
  if (t === "open_healthy_nearby") return "Healthy Nearby";
  if (t === "open_scan_camera") return "Scan Meal";
  if (t === "open_supplement_scan") return "Supplement Scan";
  if (t === "open_daily_summary") return "Daily Summary";
  if (t === "open_goal_plan") return "Goal Plan";
  return actionType || "Unknown";
}

function badge(val, color = "#9bb7ff") {
  return { backgroundColor: `${color}22`, borderColor: `${color}55`, color };
}

export function AdminOpsDashboard({ onClose }) {
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [data, setData] = useState(null);
  const [actionBusy, setActionBusy] = useState("");
  const [actionResult, setActionResult] = useState(null);
  const [adminAuthed, setAdminAuthed] = useState(false);
  const [adminUser, setAdminUser] = useState("");
  const [adminUsernameInput, setAdminUsernameInput] = useState("");
  const [adminPasswordInput, setAdminPasswordInput] = useState("");
  const [adminAuthBusy, setAdminAuthBusy] = useState(false);
  const [adminAuthError, setAdminAuthError] = useState("");
  const [adminAuthRetryAfterSec, setAdminAuthRetryAfterSec] = useState(null);
  const [coachDebugUserId, setCoachDebugUserId] = useState("");
  const [coachDebugDay, setCoachDebugDay] = useState("");
  const [coachDebug, setCoachDebug] = useState(null);
  const [coachDryRunResult, setCoachDryRunResult] = useState(null);
  const [coachRealSendResult, setCoachRealSendResult] = useState(null);
  const [coachJobHealth, setCoachJobHealth] = useState(null);

  async function refresh() {
    if (!adminAuthed) return;
    setLoading(true);
    setErr("");
    const res = await fetchOpsDashboard({ limit_targets: 20, limit_areas: 5, scan_window_days: 7 });
    if (!res.ok) {
      setErr(res.error || "failed");
      setData(null);
      setLoading(false);
      return;
    }
    setData(safeObject(res.data, {}));
    setLoading(false);
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const snap = await getAdminAuthSnapshot();
      if (cancelled) return;
      if (!snap?.hasToken) {
        setLoading(false);
        setAdminAuthed(false);
        return;
      }
      setAdminAuthBusy(true);
      const me = await adminAuthMe();
      if (cancelled) return;
      if (me?.ok) {
        setAdminAuthed(true);
        setAdminUser(String(me?.data?.username || snap?.username || "admin"));
        await refresh();
      } else {
        await clearAdminAuthState();
        setAdminAuthed(false);
        setLoading(false);
      }
      setAdminAuthBusy(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleAdminLogin() {
    if (adminAuthBusy) return;
    setAdminAuthBusy(true);
    setAdminAuthError("");
    setAdminAuthRetryAfterSec(null);
    const res = await adminLogin({ username: adminUsernameInput, password: adminPasswordInput });
    if (!res?.ok) {
      setAdminAuthed(false);
      const code = String(res?.code || "");
      if (code === "too_many_attempts") {
        const retry = Number.isFinite(Number(res?.retry_after_sec)) ? Number(res.retry_after_sec) : null;
        setAdminAuthRetryAfterSec(retry);
        setAdminAuthError("Too many login attempts. Try again later.");
      } else if (code === "invalid_credentials") {
        setAdminAuthError("Invalid admin username or password.");
      } else if (code === "admin_auth_not_configured") {
        setAdminAuthError("Admin auth is not configured on backend.");
      } else {
        setAdminAuthError(res?.error || "login_failed");
      }
      setAdminAuthBusy(false);
      return;
    }
    const me = await adminAuthMe();
    if (!me?.ok) {
      await clearAdminAuthState();
      setAdminAuthed(false);
      setAdminAuthError(me?.error || "verify_failed");
      setAdminAuthBusy(false);
      return;
    }
    setAdminPasswordInput("");
    setAdminAuthed(true);
    setAdminUser(String(me?.data?.username || adminUsernameInput || "admin"));
    setAdminAuthBusy(false);
    await refresh();
  }

  async function handleAdminLogout() {
    await clearAdminAuthState();
    setAdminAuthed(false);
    setAdminUser("");
    setData(null);
    setErr("");
    setActionResult(null);
    setCoachDebug(null);
    setCoachDryRunResult(null);
    setCoachRealSendResult(null);
    setCoachJobHealth(null);
  }

  const enrichment = safeObject(data?.enrichment, {});
  const push = safeObject(data?.push, {});
  const scan = safeObject(data?.scan, {});
  const goalCoach = safeObject(data?.goal_coach, {});

  const weakest = enrichment?.weak_suburbs?.[0] || null;
  const weakestGeneric = weakest ? num(weakest.percent_top_5_generic_fallback) : null;
  const canonicalCount = weakest ? num(weakest.canonical_trusted_local_profiles_count) : null;
  const nextCount = safeArray(enrichment?.next_targets).length;

  const rolloutMode = String(push?.rollout_mode || push?.rolloutMode || "-");
  const sendingEnabled = Boolean(push?.sending_enabled ?? push?.sendingEnabled);

  async function runAction(name, fn) {
    if (actionBusy) return;
    setActionBusy(name);
    setActionResult(null);
    try {
      const res = await fn();
      setActionResult({ name, ok: res.ok, data: res.data, error: res.error });
      if (name === "apply_next_targets" && res.ok) {
        // Refresh after enrichment mutations
        void refresh();
      }
      if (name === "coach_job_health_refresh" && res.ok) {
        setCoachJobHealth(safeObject(res.data, {}));
      }
    } finally {
      setActionBusy("");
    }
  }

  useEffect(() => {
    if (!adminAuthed) return undefined;
    let cancelled = false;
    const tick = async () => {
      if (cancelled || actionBusy) return;
      const res = await fetchCoachNudgeJobHealth();
      if (cancelled) return;
      if (res?.ok) setCoachJobHealth(safeObject(res.data, {}));
    };
    void tick();
    const id = setInterval(() => {
      void tick();
    }, 45000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [adminAuthed, actionBusy]);

  if (!adminAuthed) {
    return (
      <View style={styles.container}>
        <View style={styles.header}>
          <Text style={styles.title}>Admin Login</Text>
          <TouchableOpacity style={styles.smallBtn} onPress={onClose}>
            <Text style={styles.smallBtnText}>Close</Text>
          </TouchableOpacity>
        </View>
        <View style={{ padding: 16 }}>
          <Text style={styles.tiny}>Separate admin credentials are required.</Text>
          <TextInput
            style={[styles.input, { marginTop: 10 }]}
            placeholder="Admin username"
            placeholderTextColor="#6f86ab"
            value={adminUsernameInput}
            onChangeText={setAdminUsernameInput}
            autoCapitalize="none"
            autoCorrect={false}
          />
          <TextInput
            style={[styles.input, { marginTop: 8 }]}
            placeholder="Admin password"
            placeholderTextColor="#6f86ab"
            value={adminPasswordInput}
            onChangeText={setAdminPasswordInput}
            secureTextEntry
            autoCapitalize="none"
            autoCorrect={false}
          />
          <TouchableOpacity
            style={[styles.actionBtn, { marginTop: 10 }, adminAuthBusy ? styles.actionBtnDisabled : null]}
            disabled={adminAuthBusy}
            onPress={() => void handleAdminLogin()}
          >
            <Text style={styles.actionBtnText}>{adminAuthBusy ? "Signing in…" : "Sign in as admin"}</Text>
          </TouchableOpacity>
          {adminAuthError ? <Text style={[styles.tiny, { color: "#ffb4b4" }]}>Error: {adminAuthError}</Text> : null}
          {adminAuthRetryAfterSec != null ? (
            <Text style={[styles.tiny, { color: "#ffb4b4" }]}>Retry after: {Math.max(1, Math.round(adminAuthRetryAfterSec))}s</Text>
          ) : null}
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Admin Ops Dashboard</Text>
        <View style={{ flexDirection: "row", gap: 10 }}>
          <Text style={[styles.tiny, { marginTop: 8 }]}>as {adminUser || "admin"}</Text>
          <TouchableOpacity style={styles.smallBtn} onPress={refresh} disabled={loading}>
            <Text style={styles.smallBtnText}>Refresh</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.smallBtn} onPress={() => void handleAdminLogout()}>
            <Text style={styles.smallBtnText}>Logout</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.smallBtn} onPress={onClose}>
            <Text style={styles.smallBtnText}>Close</Text>
          </TouchableOpacity>
        </View>
      </View>

      {loading ? (
        <View style={{ padding: 16 }}>
          <ActivityIndicator />
          <Text style={styles.tiny}>Loading ops summary…</Text>
        </View>
      ) : err ? (
        <View style={{ padding: 16 }}>
          <Text style={[styles.p, { color: "#ffb4b4" }]}>Error: {String(err)}</Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 40 }}>
          {/* Top cards */}
          <View style={styles.cardRow}>
            <View style={styles.card}>
              <Text style={styles.cardKicker}>Weakest suburb</Text>
              <Text style={styles.cardValue}>{weakest?.display_name || weakest?.area_key || "-"}</Text>
              <Text style={styles.tiny}>Generic fallback: {weakestGeneric == null ? "-" : pct(weakestGeneric)}</Text>
            </View>
            <View style={styles.card}>
              <Text style={styles.cardKicker}>Canonical profiles</Text>
              <Text style={styles.cardValue}>{canonicalCount == null ? "-" : String(canonicalCount)}</Text>
              <Text style={styles.tiny}>In weakest suburb</Text>
            </View>
          </View>
          <View style={styles.cardRow}>
            <View style={styles.card}>
              <Text style={styles.cardKicker}>Next targets</Text>
              <Text style={styles.cardValue}>{String(nextCount)}</Text>
              <Text style={styles.tiny}>limit=20</Text>
            </View>
            <View style={styles.card}>
              <Text style={styles.cardKicker}>Push rollout</Text>
              <Text style={styles.cardValue}>{rolloutMode}</Text>
              <Text style={styles.tiny}>sending_enabled: {sendingEnabled ? "true" : "false"}</Text>
            </View>
          </View>
          <View style={styles.cardRow}>
            <View style={styles.card}>
              <Text style={styles.cardKicker}>Scan TTFR p50/p90</Text>
              <Text style={styles.cardValue}>
                {Math.round(num(scan?.median_time_to_first_result_ms))} / {Math.round(num(scan?.p90_time_to_first_result_ms))} ms
              </Text>
              <Text style={styles.tiny}>window_days={String(scan?.window_days || 7)}</Text>
            </View>
          </View>

          {/* Goal Coach funnel */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Goal Coach funnel</Text>
            <Text style={styles.tiny}>window_days={String(goalCoach?.window_days ?? 7)}</Text>
            <View style={styles.cardRow}>
              <View style={styles.card}>
                <Text style={styles.cardKicker}>Actions shown</Text>
                <Text style={styles.cardValue}>{String(goalCoach?.totals?.actions_shown ?? 0)}</Text>
              </View>
              <View style={styles.card}>
                <Text style={styles.cardKicker}>Click rate</Text>
                <Text style={styles.cardValue}>{pct(goalCoach?.conversion_rates?.shown_to_clicked_pct)}</Text>
              </View>
              <View style={styles.card}>
                <Text style={styles.cardKicker}>Completion rate</Text>
                <Text style={styles.cardValue}>{pct(goalCoach?.conversion_rates?.shown_to_completed_pct)}</Text>
              </View>
              <View style={styles.card}>
                <Text style={styles.cardKicker}>Best action</Text>
                <Text style={[styles.cardValue, { fontSize: 12 }]} numberOfLines={1}>
                  {goalCoachActionLabel(goalCoach?.dropoff_summary?.best_action_type)}
                </Text>
              </View>
            </View>
            <View style={[styles.row, { marginTop: 8 }]}>
              <Text style={styles.rowTitle}>Funnel</Text>
              <View style={styles.rowRight}>
                <Text style={styles.rowMetric}>shown {goalCoach?.totals?.actions_shown ?? 0}</Text>
                <Text style={styles.rowMetric}>→ clicked {goalCoach?.totals?.actions_clicked ?? 0}</Text>
                <Text style={styles.rowMetric}>→ opened {goalCoach?.totals?.destinations_opened ?? 0}</Text>
                <Text style={styles.rowMetric}>→ completed {goalCoach?.totals?.actions_completed ?? 0}</Text>
              </View>
            </View>
            <Text style={[styles.sectionTitle, { marginTop: 12, fontSize: 12 }]}>Top action types</Text>
            {(safeArray(goalCoach?.top_action_types) || []).slice(0, 5).map((row, idx) => (
              <View key={`${row.action_type || idx}`} style={styles.row}>
                <Text style={styles.rowTitle}>{goalCoachActionLabel(row.action_type)}</Text>
                <View style={styles.rowRight}>
                  <Text style={styles.rowMetric}>shown→done {pct(row.shown_to_completed_pct)}</Text>
                  <Text style={styles.rowMetric}>completed {row.completed ?? 0}</Text>
                </View>
              </View>
            ))}
            {(goalCoach?.dropoff_summary?.largest_dropoff_step || goalCoach?.dropoff_summary?.largest_dropoff_action_type) ? (
              <View style={{ marginTop: 10, padding: 10, borderWidth: 1, borderColor: "#1b2a41", borderRadius: 10 }}>
                <Text style={styles.tiny}>
                  Largest drop-off: {String(goalCoach?.dropoff_summary?.largest_dropoff_step || "-").replace(/_/g, " → ")}
                </Text>
                <Text style={styles.tiny}>
                  Weakest action: {goalCoachActionLabel(goalCoach?.dropoff_summary?.largest_dropoff_action_type)}
                </Text>
                <Text style={styles.tiny}>
                  Best action: {goalCoachActionLabel(goalCoach?.dropoff_summary?.best_action_type)}
                </Text>
              </View>
            ) : null}
          </View>

          {/* Weak suburbs */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Weak suburbs</Text>
            {safeArray(enrichment?.weak_suburbs).slice(0, 6).map((r, idx) => (
              <View key={`${r.area_key || idx}`} style={styles.row}>
                <Text style={styles.rowTitle}>{r.display_name || r.area_key}</Text>
                <View style={styles.rowRight}>
                  <Text style={styles.rowMetric}>gen {pct(r.percent_top_5_generic_fallback)}</Text>
                  <Text style={styles.rowMetric}>local {pct(r.visible_results_using_local_profiles_percent)}</Text>
                  <Text style={styles.rowMetric}>chain {pct(num(r.known_chain_hidden_rate) * 100)}</Text>
                </View>
              </View>
            ))}
          </View>

          {/* Next targets */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Next enrichment targets</Text>
            {safeArray(enrichment?.next_targets).slice(0, 12).map((t, idx) => (
              <View key={`${t.area_key || ""}:${t.place_name || idx}`} style={styles.row}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowTitle}>{t.place_name || "-"}</Text>
                  <Text style={styles.tiny}>{t.area_key} • {t.reason_summary || ""}</Text>
                </View>
                <View style={{ alignItems: "flex-end" }}>
                  <Text style={[styles.pill, badge("#7bd3ff")]}>
                    {String(t.recommended_enrichment_action || "-")}
                  </Text>
                  <Text style={styles.tiny}>score {String(t.priority_score ?? "-")}</Text>
                </View>
              </View>
            ))}
          </View>

          {/* Push */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Push rollout</Text>
            <Text style={styles.tiny}>
              enabled={String(push?.sending_enabled)} • mode={String(push?.rollout_mode)} • percent={String(push?.rollout_percent)} • active_user_days={String(push?.active_user_days)}
            </Text>
            <Text style={styles.tiny}>
              max_per_6h={String(push?.max_per_6h)} • max_per_24h={String(push?.max_per_24h)} • eligible_estimate={String(push?.batch_eligible_estimate)}
            </Text>
            <Text style={styles.tiny}>
              recent_sent={String(push?.recent_sent_count)} • receipt_ok={String(push?.recent_receipt_ok_count)} • receipt_err={String(push?.recent_receipt_error_count)}
            </Text>
          </View>

          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Coach nudge job health</Text>
            <TouchableOpacity
              style={[styles.actionBtn, actionBusy ? styles.actionBtnDisabled : null]}
              disabled={Boolean(actionBusy)}
              onPress={() =>
                runAction("coach_job_health_refresh", async () => {
                  const res = await fetchCoachNudgeJobHealth();
                  if (res?.ok) setCoachJobHealth(safeObject(res.data, {}));
                  return res;
                })
              }
            >
              <Text style={styles.actionBtnText}>
                {actionBusy === "coach_job_health_refresh" ? "Refreshing…" : "Refresh nudge job health"}
              </Text>
            </TouchableOpacity>
            {coachJobHealth ? (
              <View style={{ marginTop: 10, padding: 10, borderWidth: 1, borderColor: "#26364f", borderRadius: 10 }}>
                <Text style={styles.tiny}>status: {String(coachJobHealth?.status || "-")}</Text>
                <Text style={styles.tiny}>
                  runs_24h={String(coachJobHealth?.summary?.runs_in_window ?? "-")} • failed_24h=
                  {String(coachJobHealth?.summary?.failed_in_window ?? "-")} • running_now=
                  {String(coachJobHealth?.summary?.running_now ?? "-")}
                </Text>
                <Text style={styles.tiny}>
                  last_success={String(coachJobHealth?.summary?.last_success_at || "-")}
                </Text>
                <Text style={styles.tiny}>
                  last_failure={String(coachJobHealth?.summary?.last_failure_at || "-")}
                </Text>
                <Text style={styles.tiny}>
                  latest_run_status={String(coachJobHealth?.recent_runs?.[0]?.status || "-")} • duration_ms=
                  {String(coachJobHealth?.recent_runs?.[0]?.duration_ms ?? "-")}
                </Text>
              </View>
            ) : null}
          </View>

          {/* Scan */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Scan health</Text>
            <Text style={styles.tiny}>total_scans={String(scan?.total_scans || 0)}</Text>
            <Text style={styles.tiny}>
              TTFR p50/p90: {Math.round(num(scan?.median_time_to_first_result_ms))}/{Math.round(num(scan?.p90_time_to_first_result_ms))} ms
            </Text>
            <Text style={styles.tiny}>
              Final p50/p90: {Math.round(num(scan?.median_time_to_final_result_ms))}/{Math.round(num(scan?.p90_time_to_final_result_ms))} ms
            </Text>
            <Text style={styles.tiny}>
              vision_hit_rate={Math.round(num(scan?.vision_cache_hit_rate) * 100)}% • nutrition_hit_rate={Math.round(num(scan?.cache_hit_rate) * 100)}%
            </Text>
          </View>

          {/* Actions */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Actions (safe)</Text>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
              <TouchableOpacity
                style={[styles.actionBtn, actionBusy ? styles.actionBtnDisabled : null]}
                disabled={Boolean(actionBusy)}
                onPress={() => runAction("apply_next_targets", () => applyNextTargets({ limit: 20 }))}
              >
                <Text style={styles.actionBtnText}>
                  {actionBusy === "apply_next_targets" ? "Applying…" : "Apply next 20 targets"}
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.actionBtn, actionBusy ? styles.actionBtnDisabled : null]}
                disabled={Boolean(actionBusy)}
                onPress={() => runAction("batch_dry_run", () => runBatchDryRun({ limit_users: 100 }))}
              >
                <Text style={styles.actionBtnText}>
                  {actionBusy === "batch_dry_run" ? "Running…" : "Run batch dry-run (100)"}
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.actionBtn, actionBusy ? styles.actionBtnDisabled : null]}
                disabled={Boolean(actionBusy)}
                onPress={() => runAction("check_receipts", () => checkReceipts({ limit: 100 }))}
              >
                <Text style={styles.actionBtnText}>
                  {actionBusy === "check_receipts" ? "Checking…" : "Check pending receipts (100)"}
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.actionBtn, actionBusy ? styles.actionBtnDisabled : null]}
                disabled={Boolean(actionBusy)}
                onPress={() => runAction("auto_promote", () => runAutoPromote({ limit: 100 }))}
              >
                <Text style={styles.actionBtnText}>
                  {actionBusy === "auto_promote" ? "Promoting…" : "Run auto-promote (100)"}
                </Text>
              </TouchableOpacity>
            </View>

            {actionResult ? (
              <View style={{ marginTop: 12, padding: 10, borderWidth: 1, borderColor: "#26364f", borderRadius: 10 }}>
                <Text style={styles.tiny}>
                  last_action: {actionResult.name} • ok={String(actionResult.ok)}
                </Text>
                <Text style={styles.tiny} numberOfLines={6}>
                  {actionResult.ok ? JSON.stringify(actionResult.data || {}, null, 0) : `error: ${actionResult.error}`}
                </Text>
              </View>
            ) : null}
          </View>

          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Coach nudge debug (per user)</Text>
            <Text style={styles.tiny}>Use this to inspect final_reason instantly.</Text>
            <View style={{ gap: 8, marginTop: 8 }}>
              <TextInput
                style={styles.input}
                placeholder="user_id"
                placeholderTextColor="#6f86ab"
                value={coachDebugUserId}
                onChangeText={setCoachDebugUserId}
                autoCapitalize="none"
                autoCorrect={false}
              />
              <TextInput
                style={styles.input}
                placeholder="day (optional, YYYY-MM-DD)"
                placeholderTextColor="#6f86ab"
                value={coachDebugDay}
                onChangeText={setCoachDebugDay}
                autoCapitalize="none"
                autoCorrect={false}
              />
              <TouchableOpacity
                style={[styles.actionBtn, actionBusy ? styles.actionBtnDisabled : null]}
                disabled={Boolean(actionBusy) || !String(coachDebugUserId || "").trim()}
                onPress={() =>
                  runAction("coach_debug_user", async () => {
                    const res = await fetchCoachNudgeDebugUser({
                      user_id: String(coachDebugUserId || "").trim(),
                      day: String(coachDebugDay || "").trim(),
                    });
                    if (res?.ok) setCoachDebug(safeObject(res.data, {}));
                    else setCoachDebug({ ok: false, error: res?.error || "failed", data: res?.data });
                    return res;
                  })
                }
              >
                <Text style={styles.actionBtnText}>
                  {actionBusy === "coach_debug_user" ? "Checking…" : "Check coach nudge status"}
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.actionBtn, actionBusy ? styles.actionBtnDisabled : null]}
                disabled={Boolean(actionBusy) || !String(coachDebugUserId || "").trim()}
                onPress={() =>
                  runAction("coach_dry_run_user", async () => {
                    const res = await runCoachNudgeDryRunForUser({
                      user_id: String(coachDebugUserId || "").trim(),
                      day: String(coachDebugDay || "").trim(),
                    });
                    if (res?.ok) setCoachDryRunResult(safeObject(res.data, {}));
                    else setCoachDryRunResult({ ok: false, error: res?.error || "failed", data: res?.data });
                    return res;
                  })
                }
              >
                <Text style={styles.actionBtnText}>
                  {actionBusy === "coach_dry_run_user" ? "Sending…" : "Dry-run send nudge"}
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.actionBtn, styles.dangerBtn, actionBusy ? styles.actionBtnDisabled : null]}
                disabled={Boolean(actionBusy) || !String(coachDebugUserId || "").trim()}
                onPress={() => {
                  const uid = String(coachDebugUserId || "").trim();
                  const dayTxt = String(coachDebugDay || "").trim();
                  Alert.alert(
                    "Send real coach nudge?",
                    `This will attempt a real push now for user ${uid}${dayTxt ? ` on ${dayTxt}` : ""}.`,
                    [
                      { text: "Cancel", style: "cancel" },
                      {
                        text: "Send",
                        style: "destructive",
                        onPress: () =>
                          void runAction("coach_real_send_user", async () => {
                            const res = await runCoachNudgeRealSendForUser({
                              user_id: uid,
                              day: dayTxt,
                            });
                            if (res?.ok) setCoachRealSendResult(safeObject(res.data, {}));
                            else setCoachRealSendResult({ ok: false, error: res?.error || "failed", data: res?.data });
                            return res;
                          }),
                      },
                    ]
                  );
                }}
              >
                <Text style={styles.actionBtnText}>
                  {actionBusy === "coach_real_send_user" ? "Sending…" : "Real send nudge"}
                </Text>
              </TouchableOpacity>
            </View>
            {coachDebug ? (
              <View style={{ marginTop: 12, padding: 10, borderWidth: 1, borderColor: "#26364f", borderRadius: 10 }}>
                <Text style={styles.tiny}>final_reason: {String(coachDebug?.final_reason || coachDebug?.error || "-")}</Text>
                <Text style={styles.tiny}>
                  local_hour={String(coachDebug?.local_time?.local_hour ?? "-")} • quiet={String(
                    coachDebug?.local_time?.in_quiet_hours ?? "-"
                  )}
                </Text>
                <Text style={styles.tiny}>
                  tokens={String(coachDebug?.tokens?.active_expo_tokens_count ?? "-")} • real_send_allowed=
                  {String(coachDebug?.real_send_allowed ?? "-")}
                </Text>
                <Text style={styles.tiny}>
                  cap {String(coachDebug?.daily_cap?.sent_today ?? "-")}/{String(coachDebug?.daily_cap?.max_per_day ?? "-")} • chosen=
                  {String(coachDebug?.nudge_candidates?.chosen_type || "-")}
                </Text>
              </View>
            ) : null}
            {coachDryRunResult ? (
              <View style={{ marginTop: 10, padding: 10, borderWidth: 1, borderColor: "#26364f", borderRadius: 10 }}>
                <Text style={styles.tiny}>
                  dry_run_result: {String(coachDryRunResult?.nudge_type || coachDryRunResult?.final_suppressed_reason || coachDryRunResult?.error || "-")}
                </Text>
                <Text style={styles.tiny}>
                  attempted={String(coachDryRunResult?.notifications_attempted ?? "-")} • tickets={String(coachDryRunResult?.tickets_received ?? "-")}
                </Text>
                <Text style={styles.tiny}>
                  real_send_reason={String(coachDryRunResult?.real_send_reason || "-")} • rollout={String(coachDryRunResult?.rollout_mode || "-")}
                </Text>
              </View>
            ) : null}
            {coachRealSendResult ? (
              <View style={{ marginTop: 10, padding: 10, borderWidth: 1, borderColor: "#4a2530", borderRadius: 10 }}>
                <Text style={styles.tiny}>
                  real_send_result: {String(coachRealSendResult?.nudge_type || coachRealSendResult?.final_suppressed_reason || coachRealSendResult?.error || "-")}
                </Text>
                <Text style={styles.tiny}>
                  attempted={String(coachRealSendResult?.notifications_attempted ?? "-")} • tickets={String(coachRealSendResult?.tickets_received ?? "-")}
                </Text>
                <Text style={styles.tiny}>
                  real_send_reason={String(coachRealSendResult?.real_send_reason || "-")} • rollout={String(coachRealSendResult?.rollout_mode || "-")}
                </Text>
              </View>
            ) : null}
          </View>
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0b1220" },
  header: {
    paddingTop: 14,
    paddingBottom: 10,
    paddingHorizontal: 14,
    borderBottomWidth: 1,
    borderBottomColor: "#1b2a41",
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  title: { color: "white", fontSize: 16, fontWeight: "700" },
  smallBtn: {
    paddingVertical: 7,
    paddingHorizontal: 10,
    borderWidth: 1,
    borderColor: "#2a3d5b",
    borderRadius: 10,
    backgroundColor: "#132033",
  },
  smallBtnText: { color: "#cfe3ff", fontSize: 12, fontWeight: "600" },
  cardRow: { flexDirection: "row", gap: 12, marginBottom: 12 },
  card: {
    flex: 1,
    padding: 12,
    borderWidth: 1,
    borderColor: "#1b2a41",
    backgroundColor: "#0f1a2b",
    borderRadius: 14,
  },
  cardKicker: { color: "#9bb7ff", fontSize: 12, fontWeight: "600" },
  cardValue: { color: "white", fontSize: 16, fontWeight: "800", marginTop: 6 },
  tiny: { color: "#9ab0cf", fontSize: 12, marginTop: 6 },
  p: { color: "#cfe3ff", fontSize: 13 },
  section: { marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: "#1b2a41" },
  sectionTitle: { color: "white", fontSize: 14, fontWeight: "800", marginBottom: 8 },
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: "#162439",
  },
  rowTitle: { color: "#e7f0ff", fontSize: 13, fontWeight: "700", maxWidth: "70%" },
  rowRight: { flexDirection: "row", gap: 10 },
  rowMetric: { color: "#9ab0cf", fontSize: 12 },
  pill: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderWidth: 1,
    borderRadius: 999,
    fontSize: 11,
    fontWeight: "700",
    overflow: "hidden",
  },
  actionBtn: {
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#2a3d5b",
    backgroundColor: "#132033",
  },
  actionBtnDisabled: { opacity: 0.55 },
  actionBtnText: { color: "#cfe3ff", fontSize: 12, fontWeight: "700" },
  dangerBtn: {
    borderColor: "#5a2b37",
    backgroundColor: "#2a1117",
  },
  input: {
    borderWidth: 1,
    borderColor: "#2a3d5b",
    borderRadius: 10,
    backgroundColor: "#0e1a2a",
    color: "#e7f0ff",
    paddingHorizontal: 10,
    paddingVertical: 10,
    fontSize: 13,
  },
});
