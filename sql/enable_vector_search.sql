-- Enable pgvector extension for vector similarity search
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;

-- Add embedding columns to questions and answers
ALTER TABLE public.questions ADD COLUMN IF NOT EXISTS embedding vector(1536);
ALTER TABLE public.answers ADD COLUMN IF NOT EXISTS embedding vector(1536);

-- Create HNSW indexes for fast cosine similarity search
CREATE INDEX IF NOT EXISTS idx_questions_embedding
  ON public.questions USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_answers_embedding
  ON public.answers USING hnsw (embedding vector_cosine_ops);

-- Semantic search function: searches both question and answer embeddings,
-- returns deduplicated question IDs ranked by best similarity score.
CREATE OR REPLACE FUNCTION public.semantic_search(
  query_embedding vector(1536),
  match_threshold float DEFAULT 0.3,
  match_count int DEFAULT 20,
  p_forum_id uuid DEFAULT NULL
)
RETURNS TABLE (question_id uuid, similarity float)
LANGUAGE sql STABLE
SET search_path = public, extensions
AS $$
  SELECT sub.question_id, MAX(sub.similarity)::float as similarity
  FROM (
    -- Match against question embeddings
    SELECT q.id as question_id,
           (1 - (q.embedding <=> query_embedding))::float as similarity
    FROM public.questions q
    WHERE q.embedding IS NOT NULL
      AND 1 - (q.embedding <=> query_embedding) > match_threshold
      AND (p_forum_id IS NULL OR q.forum_id = p_forum_id)

    UNION ALL

    -- Match against answer embeddings, return parent question ID
    SELECT a.question_id,
           (1 - (a.embedding <=> query_embedding))::float as similarity
    FROM public.answers a
    JOIN public.questions q ON q.id = a.question_id
    WHERE a.embedding IS NOT NULL
      AND 1 - (a.embedding <=> query_embedding) > match_threshold
      AND (p_forum_id IS NULL OR q.forum_id = p_forum_id)
  ) sub
  GROUP BY sub.question_id
  ORDER BY similarity DESC
  LIMIT match_count;
$$;
