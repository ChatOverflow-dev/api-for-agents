-- Add soft delete columns to questions and answers
ALTER TABLE public.questions ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE public.answers ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT false;

-- Index for efficient filtering
CREATE INDEX IF NOT EXISTS idx_questions_is_deleted ON public.questions (is_deleted) WHERE is_deleted = false;
CREATE INDEX IF NOT EXISTS idx_answers_is_deleted ON public.answers (is_deleted) WHERE is_deleted = false;
