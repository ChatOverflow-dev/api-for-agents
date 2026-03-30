-- Soft delete support for questions and answers
-- The is_deleted column and filtered indexes are used by the API delete endpoints
-- which already exist in main — this migration adds the schema support.

ALTER TABLE public.questions ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE public.answers ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_questions_is_deleted ON public.questions (is_deleted) WHERE is_deleted = false;
CREATE INDEX IF NOT EXISTS idx_answers_is_deleted ON public.answers (is_deleted) WHERE is_deleted = false;
