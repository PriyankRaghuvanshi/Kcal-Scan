/**
 * Pure helpers for lunch decision cards (remaining calories/protein) and Weekly Coach summary.
 * Used to avoid contradictory UI (e.g. "0" from empty fallback when page shows remaining).
 */

function num(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/**
 * Build the remaining calories/protein line for a recommendation card.
 * Prefer page-level source of truth when card.remaining_calories is 0 but page has > 50 kcal.
 *
 * @param {object} options
 * @param {number|null} options.pageRemainingCal - Page-level remaining kcal
 * @param {number|null} options.pageRemainingProtein - Page-level remaining protein g
 * @param {number|null} options.cardRemainingCal - Per-card remaining kcal (can be 0/stale)
 * @param {number|null} options.cardRemainingProtein - Per-card remaining protein g
 * @param {number|null} options.orderCal - Estimated order calories
 * @param {number|null} options.orderProtein - Estimated order protein g
 * @returns {string|null} Display line or null if no data (never "0" from empty fallback)
 */
function buildRemainingLine({
  pageRemainingCal,
  pageRemainingProtein,
  cardRemainingCal,
  cardRemainingProtein,
  orderCal,
  orderProtein,
}) {
  const usePageLevel =
    (cardRemainingCal === 0 && pageRemainingCal != null && pageRemainingCal > 50) ||
    cardRemainingCal == null;
  const displayRemainingCal = usePageLevel ? pageRemainingCal : cardRemainingCal;
  const displayRemainingProtein = usePageLevel
    ? pageRemainingProtein
    : (num(cardRemainingProtein) != null ? num(cardRemainingProtein) : pageRemainingProtein);

  const afterOrderCal =
    orderCal != null && displayRemainingCal != null
      ? Math.max(0, Math.round(displayRemainingCal - orderCal))
      : null;
  const afterOrderProtein =
    orderProtein != null && displayRemainingProtein != null
      ? Math.max(0, Math.round(displayRemainingProtein - orderProtein))
      : null;

  if (afterOrderCal != null && afterOrderProtein != null)
    return `After this order: ${afterOrderCal} kcal left • ${afterOrderProtein}g protein left`;
  if (afterOrderCal != null) return `After this order: ${afterOrderCal} kcal left`;
  if (displayRemainingCal != null && displayRemainingProtein != null)
    return `Today left: ${Math.round(displayRemainingCal)} kcal • ${Math.round(displayRemainingProtein)}g protein`;
  if (displayRemainingCal != null) return `Today left: ${Math.round(displayRemainingCal)} kcal`;
  if (displayRemainingProtein != null) return `Today left: ${Math.round(displayRemainingProtein)}g protein`;
  return null;
}

/**
 * Build the Weekly Coach summary line (days on track, in-progress, avg protein).
 *
 * @param {object} options
 * @param {number} options.onTrackDays - Days meeting cal/protein targets
 * @param {number} options.trackedDays - Days with any meals logged
 * @param {number} options.avgProtein - Average daily protein g
 * @param {boolean} options.todayInProgress - User has logged today, week is current
 * @returns {string} Display line
 */
function buildWeeklyCoachSummaryLine({ onTrackDays, trackedDays, avgProtein, todayInProgress }) {
  const parts = [];
  if (trackedDays === 0) {
    parts.push("No days logged this week yet");
  } else {
    parts.push(`${onTrackDays}/${trackedDays} days on track`);
    if (todayInProgress && onTrackDays === 0) parts.push("Today is still in progress");
    if (avgProtein > 0) parts.push(`Avg protein ${avgProtein}g`);
  }
  return parts.join(" • ");
}

module.exports = { buildRemainingLine, buildWeeklyCoachSummaryLine, num };
