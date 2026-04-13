-- Chain match impression log.
-- Append-only: every /places/healthy response inserts one row per chain matched.
-- Powers /admin/chain-match-stats which surfaces "top N chains by user impressions"
-- so we can prioritize curation work toward chains users actually visit.
--
-- Run once in Supabase SQL editor before the chain-match instrumentation
-- code goes live (otherwise inserts silently no-op).

CREATE TABLE IF NOT EXISTS public.chain_match_events (
    id           BIGSERIAL PRIMARY KEY,
    user_id      TEXT,
    chain_key    TEXT NOT NULL,
    market_tag   TEXT,
    place_id     TEXT,
    was_top_pick BOOLEAN NOT NULL DEFAULT FALSE,
    ts           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chain_match_events_chain_ts
    ON public.chain_match_events (chain_key, ts DESC);
CREATE INDEX IF NOT EXISTS idx_chain_match_events_ts
    ON public.chain_match_events (ts DESC);
CREATE INDEX IF NOT EXISTS idx_chain_match_events_user_ts
    ON public.chain_match_events (user_id, ts DESC) WHERE user_id IS NOT NULL;

-- Optional: row-level retention. Drop rows older than 180 days. Run periodically
-- via a Supabase Scheduled Function or just whenever you remember.
--   DELETE FROM public.chain_match_events WHERE ts < now() - INTERVAL '180 days';
