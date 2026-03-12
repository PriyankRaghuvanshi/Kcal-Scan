# User Venue Contributions

## Goal

Capture user suggestions for local venues (better orders, veg/vegan options, accuracy feedback). All submissions are stored immediately. Safe, repeated contributions can auto-promote into trusted local venue profiles; only conflicts and risky cases remain for manual review.

## Trust Layers

| Layer | Description | Used for live ranking |
|-------|-------------|------------------------|
| **A. Raw contributions** | All submissions stored immediately. No blocking. | No |
| **B. Aggregated evidence** | Per place + normalized suggestion + diet context. Counts, conflict signals. | No |
| **C. Trusted local venue profiles** | Only auto-promoted or explicitly approved. | Yes |

## Contribution Types

| Type | Purpose |
|------|---------|
| `better_order_suggestion` | User suggests a better order (e.g. "Paneer tikka + dal") |
| `item_not_on_menu` | User reports an item is not on the menu |
| `vegetarian_option_missing` | Vegetarian user reports no veg option |
| `vegan_option_missing` | Vegan user reports no vegan option |
| `recommendation_accurate` | User confirms recommendation was accurate |
| `recommendation_inaccurate` | User reports recommendation was wrong |

## Creating Contributions

**POST `/venue-contributions`**

Payload:
- `place_id` (optional)
- `place_name` (required)
- `area_key` (required)
- `contribution_type` (required)
- `user_id` (optional)
- `payload` (optional) – e.g. `{ "suggested_order": "..." }`, `{ "item_key": "..." }`

## Storage

- Store: `backend/data/user_venue_contributions.json`
- Override: `USER_VENUE_CONTRIBUTIONS_PATH`
- Schema: contributions list with status (pending, accepted, rejected)

## Review Flow

See [CONTRIBUTION_REVIEW_FLOW.md](CONTRIBUTION_REVIEW_FLOW.md) for:

- List pending: `GET /venue-contributions/pending`
- Review bundle: `GET /venue-contributions/review-bundle?contribution_id=...`
- Approve: `POST /venue-contributions/review/approve`
- Reject: `POST /venue-contributions/review/reject`

## Integration with Local Venue Profiles

**Manual review:** Approved contributions of type `accept_as_new_template` add candidate templates to local venue profiles.

**Auto-promotion:** Evidence-based auto-promotion can promote safe, repeated contributions without manual review. See [CONTRIBUTION_AUTO_PROMOTION.md](CONTRIBUTION_AUTO_PROMOTION.md) for thresholds, blockers, and diet-safe rules. Run via `POST /venue-contributions/auto-promote/run`.

Profiles are stored in `backend/data/local_venue_profiles.json` and used by `local_venue_enrichment.py` for Healthy Nearby recommendations.

## Key Files

- `backend/user_venue_contributions.py` – store, create, list, update status
- `backend/contribution_review_flow.py` – review and apply
- `backend/local_venue_profiles.py` – profile mutations
