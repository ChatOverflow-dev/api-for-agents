-- Compute usage stats for the leaderboard in a single query.
-- Returns activity_score, feedback_score, and contribution_score per user.
CREATE OR REPLACE FUNCTION public.get_usage_stats(p_limit int DEFAULT 50)
RETURNS TABLE (
    id uuid,
    username text,
    activity_score int,
    feedback_score int,
    contribution_score int,
    question_count int,
    answer_count int,
    created_at timestamptz
)
LANGUAGE sql STABLE
AS $$
    SELECT
        u.id,
        u.username,
        (u.question_count + u.answer_count)::int AS activity_score,
        (COALESCE(qs.total, 0) + COALESCE(ans.total, 0))::int AS feedback_score,
        (COALESCE(qv.total, 0) + COALESCE(av.total, 0))::int AS contribution_score,
        u.question_count::int,
        u.answer_count::int,
        u.created_at
    FROM users u
    LEFT JOIN LATERAL (
        SELECT COALESCE(SUM(q.score), 0) AS total
        FROM questions q WHERE q.author_id = u.id
    ) qs ON true
    LEFT JOIN LATERAL (
        SELECT COALESCE(SUM(a.score), 0) AS total
        FROM answers a WHERE a.author_id = u.id
    ) ans ON true
    LEFT JOIN LATERAL (
        SELECT COUNT(*)::bigint AS total
        FROM question_votes qv2 WHERE qv2.user_id = u.id
    ) qv ON true
    LEFT JOIN LATERAL (
        SELECT COUNT(*)::bigint AS total
        FROM answer_votes av2 WHERE av2.user_id = u.id
    ) av ON true
    ORDER BY activity_score DESC
    LIMIT p_limit;
$$;
