const REDACT_KEYS = ["token", "authorization", "password", "secret", "email", "phone", "jwt", "key"];

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function redactValue(key, value) {
  const k = String(key || "").toLowerCase();
  if (REDACT_KEYS.some((part) => k.includes(part))) return "[redacted]";
  if (typeof value === "string" && value.length > 220) return `${value.slice(0, 220)}...`;
  if (Array.isArray(value)) return value.slice(0, 20).map((item) => redactValue("", item));
  if (isPlainObject(value)) {
    const out = {};
    Object.keys(value)
      .slice(0, 40)
      .forEach((childKey) => {
        out[childKey] = redactValue(childKey, value[childKey]);
      });
    return out;
  }
  return value;
}

export function safeParseJson(value, fallback = null, label = "json") {
  try {
    if (value == null || value === "") return fallback;
    if (typeof value === "string") return JSON.parse(value);
    if (typeof value === "object") return value;
    return fallback;
  } catch (e) {
    if (typeof __DEV__ !== "undefined" && __DEV__) {
      // eslint-disable-next-line no-console
      console.log("[StartupSafe] parse failed", label, String(e?.message || e));
    }
    return fallback;
  }
}

export function safeArray(value) {
  return Array.isArray(value) ? value : [];
}

export function safeObject(value, fallback = {}) {
  return isPlainObject(value) ? value : fallback;
}

export function safeNumber(value, fallback = null) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

export function safeGetSmartAlertPayload(raw) {
  const src = safeObject(raw, {});
  return {
    alert_id: String(src.alert_id || "").trim(),
    alert_type: String(src.alert_type || "").trim(),
    place_id: String(src.place_id || "").trim(),
    place_name: String(src.place_name || "").trim(),
    best_item_name: String(src.best_item_name || "").trim(),
    route_target: String(src.route_target || "smart_alert_inbox").trim() || "smart_alert_inbox",
    deep_link: String(src.deep_link || "").trim(),
    context_mode: String(src.context_mode || "").trim(),
    display_rank_score_100: safeNumber(src.display_rank_score_100, null),
    place_lat: safeNumber(src.place_lat, null),
    place_lng: safeNumber(src.place_lng, null),
    confidence_label: String(src.confidence_label || "").trim(),
    recommendation_label: String(src.recommendation_label || "").trim(),
    chosen_candidate_specificity_tier: String(src.chosen_candidate_specificity_tier || "").trim(),
    menu_item_source: String(src.menu_item_source || "").trim(),
    local_profile_source: String(src.local_profile_source || "").trim(),
    matched_local_profile: src.matched_local_profile === true,
    used_venue_intelligence_cache: src.used_venue_intelligence_cache === true,
    best_item_is_generic_fallback: src.best_item_is_generic_fallback === true,
  };
}

export function safeGetOpsDashboardSummary(raw) {
  const src = safeObject(raw, {});
  const enrichment = safeObject(src.enrichment, {});
  const push = safeObject(src.push, {});
  const scan = safeObject(src.scan, {});
  return {
    enrichment: {
      weak_suburbs: safeArray(enrichment.weak_suburbs),
      next_targets: safeArray(enrichment.next_targets),
    },
    push,
    scan,
  };
}

export function createLaunchTracer(tag = "startup") {
  const marks = [];
  const tracerTag = String(tag || "startup");
  const mark = (phase, detail) => {
    const entry = {
      t: Date.now(),
      phase: String(phase || "unknown"),
      detail: redactValue("detail", detail ?? null),
    };
    marks.push(entry);
    if (typeof __DEV__ !== "undefined" && __DEV__) {
      // eslint-disable-next-line no-console
      console.log(`[LaunchTrace:${tracerTag}]`, entry.phase, entry.detail || "");
    }
  };
  const getLastPhase = () => (marks.length ? marks[marks.length - 1].phase : "boot_unknown");
  const getMarks = () => [...marks];
  return { mark, getLastPhase, getMarks };
}

export function installGlobalErrorHandler(getContext) {
  const errorUtils = global?.ErrorUtils;
  if (!errorUtils || typeof errorUtils.getGlobalHandler !== "function" || typeof errorUtils.setGlobalHandler !== "function") {
    return () => {};
  }
  const prev = errorUtils.getGlobalHandler();
  errorUtils.setGlobalHandler((error, isFatal) => {
    try {
      const ctx = typeof getContext === "function" ? getContext() : {};
      const safeCtx = redactValue("context", safeObject(ctx, {}));
      // eslint-disable-next-line no-console
      console.log("[GlobalError]", {
        isFatal: Boolean(isFatal),
        message: String(error?.message || error || "unknown"),
        name: String(error?.name || "Error"),
        context: safeCtx,
      });
    } catch {}

    if (typeof prev === "function") {
      try {
        prev(error, isFatal);
      } catch {}
    }
  });

  return () => {
    try {
      errorUtils.setGlobalHandler(prev);
    } catch {}
  };
}
