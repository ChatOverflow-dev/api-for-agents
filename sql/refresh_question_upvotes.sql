BEGIN;

-- Wrap the recalculation and update in a single transaction so the cache
-- cannot observe a partially updated state. This refreshes upvotes,
-- downvotes, and the derived score column for every question.
WITH vote_totals AS (
    SELECT q.id AS question_id,
           COUNT(v.*) FILTER (WHERE v.vote_type = 'up') AS upvote_count,
           COUNT(v.*) FILTER (WHERE v.vote_type = 'down') AS downvote_count
    FROM public.questions AS q
    LEFT JOIN public.question_votes AS v
      ON v.question_id = q.id
    GROUP BY q.id
)
UPDATE public.questions AS q
SET upvote_count = vt.upvote_count,
    downvote_count = vt.downvote_count,
    score = vt.upvote_count - vt.downvote_count
FROM vote_totals AS vt
WHERE q.id = vt.question_id;

COMMIT;
