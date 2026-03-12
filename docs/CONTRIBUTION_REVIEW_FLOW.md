# Contribution Review Flow

## Goal

Safe human-in-the-loop workflow for user venue contributions. Approved contributions update local venue profiles; nothing is auto-merged. No LLM on the hot path.

## Review States

| Status | Meaning |
|--------|---------|
| `pending` | Awaiting review |
| `accepted` | Approved and applied (or note-only) |
| `rejected` | Rejected with reviewer notes |

## Action Types

| Action | Use case | Effect |
|--------|----------|--------|
| `accept_as_new_template` | better_order_suggestion, vegetarian_option_missing, vegan_option_missing | Adds new candidate template to profile (or creates profile) |
| `accept_as_template_update` | Update existing template | Updates confidence, inactive, notes on existing template |
| `accept_as_swap` | Add swap suggestion | Adds swap template to profile |
| `accept_as_note_only` | Acknowledge without change | Marks accepted, no profile update |
| `accept_mark_inaccurate_previous` | item_not_on_menu | Marks existing template inactive |
| `reject` | Decline contribution | Status = rejected, reviewer_notes preserved |

## Contribution Types

| Type | Typical approval action |
|------|-------------------------|
| `better_order_suggestion` | accept_as_new_template |
| `item_not_on_menu` | accept_mark_inaccurate_previous |
| `vegetarian_option_missing` | accept_as_new_template (with diet_tags: ["vegetarian"]) |
| `vegan_option_missing` | accept_as_new_template (with diet_tags: ["vegan"]) |
| `recommendation_accurate` | accept_as_note_only or accept_as_template_update |
| `recommendation_inaccurate` | accept_mark_inaccurate_previous |

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/venue-contributions` | Create contribution |
| GET | `/venue-contributions/pending?area_key=...&limit=...` | List pending |
| GET | `/venue-contributions/review-bundle?contribution_id=...` | Get review bundle |
| POST | `/venue-contributions/review/approve` | Approve with action |
| POST | `/venue-contributions/review/reject` | Reject with notes |

## Approve Payload Example

```json
{
  "contribution_id": "...",
  "reviewer_id": "admin_1",
  "action_type": "accept_as_new_template",
  "template_payload": {
    "template_key": "paneer_tikka_dal",
    "template_name": "Paneer tikka + dal",
    "estimated_calories": 620,
    "estimated_protein_g": 31,
    "cut_friendly": true,
    "food_quality_tags": ["high_protein"],
    "diet_tags": ["vegetarian"]
  },
  "reviewer_notes": "Looks plausible for this venue"
}
```

## Reject Payload Example

```json
{
  "contribution_id": "...",
  "reviewer_id": "admin_1",
  "reviewer_notes": "Too vague / insufficient evidence"
}
```

## Safe Apply Rules

- **Create new template** when safer than mutating an existing one
- **Update existing** only when action_type is `accept_as_template_update`
- **Do not delete** templates; use `inactive: true` transitions
- **Audit trail** stores review_id, contribution_id, place_id, action_type, applied_changes
- **Diet-safe** vegetarian/vegan contributions add/preserve diet_tags and vegetarian_possible/vegan_possible

## Diet-Aware Handling

- `vegetarian_option_missing` → approval adds template with `diet_tags: ["vegetarian"]`, `vegetarian_possible: true`
- `vegan_option_missing` → approval adds template with `diet_tags: ["vegan"]`, `vegan_possible: true`, `vegetarian_possible: true`
- Vegan suggestions must not inherit dairy/egg defaults
- `_ensure_diet_tags()` in approval flow enforces diet-safe semantics

## Review Bundle

For each contribution under review, the bundle includes:

- contribution fields
- place_id, place_name, area_key
- existing_profile (if present)
- existing_candidate_templates
- existing_swap_templates
- recent_related_contributions
- specificity_tier, profile_source
- contribution_count_for_place, pending_count_for_place

## Audit Trail

Stored in `backend/data/contribution_review_audit.json` (override: `CONTRIBUTION_REVIEW_AUDIT_PATH`):

- review_id
- contribution_id
- place_id
- reviewer_id
- action_type
- applied_changes (JSON)
- created_at

## Key Files

- `backend/user_venue_contributions.py` – contribution store
- `backend/contribution_review_flow.py` – review helpers, approve/reject
- `backend/local_venue_profiles.py` – add_candidate_template, add_swap_template, update_template_in_profile
- `backend/main.py` – endpoints
- `docs/USER_VENUE_CONTRIBUTIONS.md` – contribution capture
- `docs/LOCAL_VENUE_ENRICHMENT.md` – profile schema and enrichment
