import React, { useEffect, useMemo, useState } from "react";
import { View, Text, TouchableOpacity, ScrollView, ActivityIndicator, StyleSheet } from "react-native";
import { fetchOpsDashboard, applyNextTargets, runBatchDryRun, checkReceipts, runAutoPromote } from "../adminOpsApi";

function num(x, d = 0) {
  const n = Number(x);
  return Number.isFinite(n) ? n : d;
}

function pct(x) {
  const n = Number(x);
  if (!Number.isFinite(n)) return "-";
  return `${Math.round(n)}%`;
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

  async function refresh() {
    setLoading(true);
    setErr("");
    const res = await fetchOpsDashboard({ limit_targets: 20, limit_areas: 5, scan_window_days: 7 });
    if (!res.ok) {
      setErr(res.error || "failed");
      setData(null);
      setLoading(false);
      return;
    }
    setData(res.data || null);
    setLoading(false);
  }

  useEffect(() => {
    void refresh();
  }, []);

  const enrichment = data?.enrichment || {};
  const push = data?.push || {};
  const scan = data?.scan || {};

  const weakest = enrichment?.weak_suburbs?.[0] || null;
  const weakestGeneric = weakest ? num(weakest.percent_top_5_generic_fallback) : null;
  const canonicalCount = weakest ? num(weakest.canonical_trusted_local_profiles_count) : null;
  const nextCount = Array.isArray(enrichment?.next_targets) ? enrichment.next_targets.length : 0;

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
    } finally {
      setActionBusy("");
    }
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Admin Ops Dashboard</Text>
        <View style={{ flexDirection: "row", gap: 10 }}>
          <TouchableOpacity style={styles.smallBtn} onPress={refresh} disabled={loading}>
            <Text style={styles.smallBtnText}>Refresh</Text>
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

          {/* Weak suburbs */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Weak suburbs</Text>
            {(enrichment?.weak_suburbs || []).slice(0, 6).map((r, idx) => (
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
            {(enrichment?.next_targets || []).slice(0, 12).map((t, idx) => (
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
});

