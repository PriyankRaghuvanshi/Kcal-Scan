/**
 * YieldPilot Connected Frontend — internal case workflow + approval pipeline + memo export.
 * For internal review and documentation only. Not client-facing advice.
 *
 * Requires: React, global fetch. Optional: base URL via env or prop.
 */

import React, { useCallback, useEffect, useState } from "react";

const STATUS_LABELS: Record<string, string> = {
  draft: "Draft",
  under_review: "Under review",
  approved: "Approved internally",
  rejected: "Rejected",
  archived: "Archived",
};

const DEFAULT_API_BASE = typeof process !== "undefined" && (process as unknown as { env?: { REACT_APP_YIELDPILOT_API?: string } }).env?.REACT_APP_YIELDPILOT_API
  || (typeof window !== "undefined" && (window as unknown as { __YIELDPILOT_API_BASE__?: string }).__YIELDPILOT_API_BASE__)
  || "";

export type CaseRecord = {
  id: number;
  user_id: string;
  profile_id?: string | null;
  symbol: string;
  contract_symbol?: string | null;
  scenario_type?: string | null;
  created_at: string;
  updated_at: string;
  status: string;
  title?: string | null;
  summary?: string | null;
  rationale?: string | null;
  blocked?: boolean;
  blocked_reason?: string | null;
  model_score?: number | null;
  capital_required?: number | null;
  expected_monthly_income?: number | null;
  recommendation_snapshot_json?: Record<string, unknown> | null;
  portfolio_guardrail_status?: string | null;
  portfolio_guardrail_reasons_json?: { reasons?: string[] } | null;
  tags_json?: string[] | null;
  [k: string]: unknown;
};

export type CaseComment = {
  id: number;
  case_id: number;
  user_id: string;
  created_at: string;
  body: string;
};

export type StatusEvent = {
  id: number;
  case_id: number;
  user_id: string;
  created_at: string;
  old_status: string | null;
  new_status: string;
  note: string | null;
};

export type YieldPilotConnectedFrontendProps = {
  apiBase?: string;
  userId: string;
  profileName?: string;
  /** Optional: pass a live recommendation to show "Create case" on a card */
  liveRecommendation?: Record<string, unknown> | null;
  onCaseCreated?: (caseRecord: CaseRecord) => void;
};

export function YieldPilotConnectedFrontend({
  apiBase = DEFAULT_API_BASE,
  userId,
  profileName,
  liveRecommendation,
  onCaseCreated,
}: YieldPilotConnectedFrontendProps) {
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<number | null>(null);
  const [detail, setDetail] = useState<CaseRecord | null>(null);
  const [comments, setComments] = useState<CaseComment[]>([]);
  const [statusHistory, setStatusHistory] = useState<StatusEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rationaleEdit, setRationaleEdit] = useState("");
  const [newComment, setNewComment] = useState("");
  const [newStatus, setNewStatus] = useState("");
  const [creatingFromRec, setCreatingFromRec] = useState(false);

  const base = (apiBase || "").replace(/\/$/, "");
  const headers: Record<string, string> = { "Content-Type": "application/json", "X-User-Id": userId };

  const fetchCases = useCallback(async () => {
    if (!base) return;
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`${base}/yieldpilot/cases?limit=100`, { headers });
      if (!r.ok) throw new Error(r.statusText);
      const data = await r.json();
      setCases(data.cases || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load cases");
      setCases([]);
    } finally {
      setLoading(false);
    }
  }, [base, userId]);

  useEffect(() => { fetchCases(); }, [fetchCases]);

  const fetchCaseDetail = useCallback(async (id: number) => {
    if (!base) return;
    setLoading(true);
    setError(null);
    try {
      const [cr, cm, sh] = await Promise.all([
        fetch(`${base}/yieldpilot/cases/${id}`, { headers }).then((r) => r.ok ? r.json() : null),
        fetch(`${base}/yieldpilot/cases/${id}/comments`, { headers }).then((r) => r.ok ? r.json() : { comments: [] }),
        fetch(`${base}/yieldpilot/cases/${id}/status-history`, { headers }).then((r) => r.ok ? r.json() : { status_history: [] }),
      ]);
      const caseRecord = cr?.case ?? null;
      setDetail(caseRecord);
      setRationaleEdit(caseRecord?.rationale ?? "");
      setComments((cm?.comments ?? []) as CaseComment[]);
      setStatusHistory((sh?.status_history ?? []) as StatusEvent[]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load case");
      setDetail(null);
    } finally {
      setLoading(false);
    }
  }, [base, userId]);

  useEffect(() => {
    if (selectedCaseId != null) fetchCaseDetail(selectedCaseId);
    else {
      setDetail(null);
      setComments([]);
      setStatusHistory([]);
    }
  }, [selectedCaseId, fetchCaseDetail]);

  const createCaseFromRecommendation = useCallback(async () => {
    if (!base || !liveRecommendation) return;
    setCreatingFromRec(true);
    setError(null);
    try {
      const r = await fetch(`${base}/yieldpilot/cases/from-recommendation`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          recommendation: liveRecommendation,
          title: (liveRecommendation.symbol || liveRecommendation.underlying) + " – " + (liveRecommendation.scenario_type || "scenario"),
        }),
      });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
      const data = await r.json();
      const caseRecord = data.case as CaseRecord;
      onCaseCreated?.(caseRecord);
      await fetchCases();
      setSelectedCaseId(caseRecord.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create case");
    } finally {
      setCreatingFromRec(false);
    }
  }, [base, userId, liveRecommendation, fetchCases, onCaseCreated]);

  const saveRationale = useCallback(async () => {
    if (!base || detail?.id == null) return;
    try {
      const r = await fetch(`${base}/yieldpilot/cases/${detail.id}`, {
        method: "PATCH",
        headers,
        body: JSON.stringify({ rationale: rationaleEdit }),
      });
      if (!r.ok) throw new Error(r.statusText);
      const data = await r.json();
      setDetail(data.case);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save rationale");
    }
  }, [base, userId, detail?.id, rationaleEdit]);

  const postComment = useCallback(async () => {
    if (!base || detail?.id == null || !newComment.trim()) return;
    try {
      const r = await fetch(`${base}/yieldpilot/cases/${detail.id}/comment`, {
        method: "POST",
        headers,
        body: JSON.stringify({ body: newComment.trim() }),
      });
      if (!r.ok) throw new Error(r.statusText);
      setNewComment("");
      const data = await r.json();
      setComments((prev) => [...prev, data.comment]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to post comment");
    }
  }, [base, userId, detail?.id, newComment]);

  const changeStatus = useCallback(async () => {
    if (!base || detail?.id == null || !newStatus) return;
    try {
      const r = await fetch(`${base}/yieldpilot/cases/${detail.id}/status`, {
        method: "POST",
        headers,
        body: JSON.stringify({ new_status: newStatus, note: "Status change from UI" }),
      });
      if (!r.ok) throw new Error(r.statusText);
      const data = await r.json();
      setDetail(data.case);
      setNewStatus("");
      await fetchCaseDetail(detail.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update status");
    }
  }, [base, userId, detail?.id, newStatus, fetchCaseDetail]);

  const downloadMemo = useCallback(async (format: "json" | "csv" | "txt") => {
    if (!base || detail?.id == null) return;
    try {
      const r = await fetch(`${base}/yieldpilot/cases/${detail.id}/memo.${format}`, { headers });
      if (!r.ok) throw new Error(r.statusText);
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `case-${detail.id}-memo.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to download memo");
    }
  }, [base, userId, detail?.id]);

  if (!base) {
    return (
      <div className="yp-section" style={styles.section}>
        <p>YieldPilot API base URL not configured. Set REACT_APP_YIELDPILOT_API or __YIELDPILOT_API_BASE__.</p>
      </div>
    );
  }

  return (
    <div className="yp-connected" style={styles.container}>
      <section className="yp-section" style={styles.section}>
        <h2 style={styles.h2}>Cases / Review Workflow</h2>
        <p style={styles.helper}>Internal workflow record only. For internal review and documentation.</p>
        {error && <div className="yp-error" style={styles.error}>{error}</div>}

        {liveRecommendation && (
          <div className="yp-create-from-rec" style={styles.card}>
            <h3 style={styles.h3}>From current scenario</h3>
            <button
              type="button"
              className="yp-btn yp-btn-primary"
              style={styles.btnPrimary}
              onClick={createCaseFromRecommendation}
              disabled={creatingFromRec}
            >
              {creatingFromRec ? "Creating…" : "Create case"}
            </button>
          </div>
        )}

        <div className="yp-case-list" style={styles.card}>
          <h3 style={styles.h3}>Case list</h3>
          {loading && !detail ? <p>Loading…</p> : null}
          {!loading && cases.length === 0 ? <p>No cases yet.</p> : null}
          {cases.length > 0 && (
            <table className="yp-table" style={styles.table}>
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Symbol</th>
                  <th>Scenario</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Model score</th>
                  <th>Capital</th>
                  <th>Profile</th>
                </tr>
              </thead>
              <tbody>
                {cases.map((c) => (
                  <tr key={c.id} onClick={() => setSelectedCaseId(c.id)} style={styles.rowClick}>
                    <td>{(c.title ?? "").slice(0, 40)}</td>
                    <td>{c.symbol}</td>
                    <td>{c.scenario_type ?? "—"}</td>
                    <td>
                      <span className="yp-badge" style={styles.badge}>
                        {STATUS_LABELS[c.status] ?? c.status}
                      </span>
                    </td>
                    <td>{c.created_at ? new Date(c.created_at).toLocaleDateString() : "—"}</td>
                    <td>{c.model_score != null ? c.model_score : "—"}</td>
                    <td>{c.capital_required != null ? c.capital_required.toLocaleString() : "—"}</td>
                    <td>{profileName ?? (c.profile_id ?? "—")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {selectedCaseId != null && (
        <section className="yp-section yp-detail" style={styles.section}>
          <button type="button" className="yp-btn" style={styles.btn} onClick={() => setSelectedCaseId(null)}>
            ← Back to list
          </button>
          {loading && detail == null ? <p>Loading case…</p> : null}
          {detail && (
            <>
              <div className="yp-committee-pack" style={styles.card}>
                <h3 style={styles.h3}>Committee pack summary</h3>
                <ul style={styles.ul}>
                  <li><strong>Top scenario:</strong> {detail.symbol} – {detail.scenario_type ?? "—"}</li>
                  <li><strong>Why ranked:</strong> Model score {detail.model_score ?? "—"}; quality/trend in snapshot.</li>
                  <li><strong>Blocked / allowed:</strong> {detail.blocked ? `Blocked: ${detail.blocked_reason ?? "—"}` : "Not blocked"}</li>
                  <li><strong>Event risk:</strong> {detail.event_risk_score != null ? detail.event_risk_score : "—"}</li>
                  <li><strong>Capital vs budget:</strong> {detail.capital_required != null ? detail.capital_required.toLocaleString() : "—"}</li>
                  <li><strong>Review status:</strong> {STATUS_LABELS[detail.status] ?? detail.status}</li>
                </ul>
              </div>

              <div className="yp-detail-card" style={styles.card}>
                <h3 style={styles.h3}>{detail.title ?? detail.symbol}</h3>
                <p><strong>Symbol:</strong> {detail.symbol} | <strong>Scenario:</strong> {detail.scenario_type ?? "—"} | <strong>Status:</strong>{" "}
                  <span className="yp-badge" style={styles.badge}>{STATUS_LABELS[detail.status] ?? detail.status}</span></p>
                {detail.recommendation_snapshot_json && (
                  <div className="yp-snapshot" style={styles.snapshot}>
                    <h4 style={styles.h4}>Frozen recommendation snapshot</h4>
                    <pre style={styles.pre}>{JSON.stringify(detail.recommendation_snapshot_json, null, 2)}</pre>
                  </div>
                )}
                <div className="yp-scores">
                  <h4 style={styles.h4}>Signal scores</h4>
                  <p>Model: {detail.model_score ?? "—"} | Trend: {detail.trend_score ?? "—"} | Quality: {detail.quality_score ?? "—"} | Event risk: {detail.event_risk_score ?? "—"}</p>
                </div>
                <div className="yp-earnings">
                  <h4 style={styles.h4}>Earnings context</h4>
                  <p>Next earnings: {detail.next_earnings_date ?? "—"} | Days away: {detail.earnings_days_away ?? "—"}</p>
                </div>
                <div className="yp-guardrail">
                  <h4 style={styles.h4}>Guardrail context</h4>
                  <p>Status: {detail.portfolio_guardrail_status ?? "—"}</p>
                  {detail.portfolio_guardrail_reasons_json?.reasons?.length ? (
                    <ul style={styles.ul}>{detail.portfolio_guardrail_reasons_json.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
                  ) : null}
                </div>
                <div className="yp-rationale">
                  <h4 style={styles.h4}>Rationale</h4>
                  <textarea
                    value={rationaleEdit}
                    onChange={(e) => setRationaleEdit(e.target.value)}
                    rows={4}
                    style={styles.textarea}
                  />
                  <button type="button" className="yp-btn" style={styles.btn} onClick={saveRationale}>Save rationale</button>
                </div>
                <div className="yp-tags" style={styles.tags}>
                  {(detail.tags_json ?? []).map((t) => (
                    <span key={t} className="yp-badge" style={styles.badge}>{t}</span>
                  ))}
                </div>
              </div>

              <div className="yp-comments" style={styles.card}>
                <h3 style={styles.h3}>Comments</h3>
                {comments.map((c) => (
                  <div key={c.id} style={styles.comment}>
                    <small>{c.created_at} – {c.user_id}</small>
                    <p>{c.body}</p>
                  </div>
                ))}
                <textarea value={newComment} onChange={(e) => setNewComment(e.target.value)} placeholder="Add a comment" rows={2} style={styles.textarea} />
                <button type="button" className="yp-btn" style={styles.btn} onClick={postComment} disabled={!newComment.trim()}>Post comment</button>
              </div>

              <div className="yp-status-history" style={styles.card}>
                <h3 style={styles.h3}>Status history</h3>
                {statusHistory.map((e) => (
                  <div key={e.id} style={styles.comment}>
                    <small>{e.created_at}: {e.old_status ?? "—"} → {e.new_status} {e.note ? `(${e.note})` : ""}</small>
                  </div>
                ))}
                <div style={styles.statusChange}>
                  <select value={newStatus} onChange={(e) => setNewStatus(e.target.value)} style={styles.select}>
                    <option value="">Change status…</option>
                    {["draft", "under_review", "approved", "rejected", "archived"].map((s) => (
                      <option key={s} value={s}>{STATUS_LABELS[s] ?? s}</option>
                    ))}
                  </select>
                  <button type="button" className="yp-btn" style={styles.btn} onClick={changeStatus} disabled={!newStatus}>Update status</button>
                </div>
              </div>

              <div className="yp-memo-export" style={styles.card}>
                <h3 style={styles.h3}>Memo export</h3>
                <button type="button" className="yp-btn" style={styles.btn} onClick={() => downloadMemo("json")}>Export memo JSON</button>
                <button type="button" className="yp-btn" style={styles.btn} onClick={() => downloadMemo("csv")}>Export memo CSV</button>
                <button type="button" className="yp-btn" style={styles.btn} onClick={() => downloadMemo("txt")}>Export memo text</button>
              </div>
            </>
          )}
        </section>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: { maxWidth: 960, margin: "0 auto", padding: 16 },
  section: { marginBottom: 24 },
  h2: { fontSize: "1.25rem", marginBottom: 8 },
  h3: { fontSize: "1rem", marginBottom: 8 },
  h4: { fontSize: "0.9rem", marginTop: 12, marginBottom: 4 },
  helper: { color: "#666", fontSize: "0.875rem", marginBottom: 12 },
  error: { background: "#fee", padding: 8, borderRadius: 4, marginBottom: 12 },
  card: { border: "1px solid #ddd", borderRadius: 8, padding: 16, marginBottom: 16 },
  table: { width: "100%", borderCollapse: "collapse" },
  rowClick: { cursor: "pointer" },
  badge: { display: "inline-block", padding: "2px 8px", borderRadius: 4, background: "#e0e0e0", fontSize: "0.85rem" },
  btn: { padding: "6px 12px", marginRight: 8, marginTop: 8 },
  btnPrimary: { padding: "8px 16px", background: "#1976d2", color: "#fff", border: "none", borderRadius: 4 },
  snapshot: { background: "#f5f5f5", padding: 12, borderRadius: 4, overflow: "auto" },
  pre: { margin: 0, fontSize: "0.8rem", whiteSpace: "pre-wrap" },
  ul: { margin: "4px 0", paddingLeft: 20 },
  textarea: { width: "100%", maxWidth: 400, marginTop: 4 },
  comment: { marginBottom: 12, paddingBottom: 12, borderBottom: "1px solid #eee" },
  statusChange: { display: "flex", gap: 8, alignItems: "center", marginTop: 12 },
  select: { padding: 6 },
  tags: { display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 },
};

export default YieldPilotConnectedFrontend;
