-- Per-user clarification memory (meal tokens + cmp:: component keys).
-- Apply in Supabase SQL editor or via migration runner.

CREATE TABLE IF NOT EXISTS public.user_ingredient_choices (
    user_id text NOT NULL,
    food_key text NOT NULL,
    choices jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT user_ingredient_choices_pkey PRIMARY KEY (user_id, food_key)
);

CREATE INDEX IF NOT EXISTS idx_user_ingredient_choices_user_id
    ON public.user_ingredient_choices (user_id);

COMMENT ON TABLE public.user_ingredient_choices IS
    'Merged scan clarification answers; food_key matches local tokens (e.g. full meal label or cmp::oatmeal).';
