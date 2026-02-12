--
-- PostgreSQL database dump
--


-- Dumped from database version 17.6
-- Dumped by pg_dump version 18.1

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA public;


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS 'standard public schema';


--
-- Name: current_user_id(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.current_user_id() RETURNS uuid
    LANGUAGE sql STABLE
    AS $$
    SELECT NULLIF(current_setting('app.current_user_id', true), '')::UUID;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: answer_votes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.answer_votes (
    user_id uuid NOT NULL,
    answer_id uuid NOT NULL,
    vote_type text NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT answer_votes_vote_type_check CHECK ((vote_type = ANY (ARRAY['up'::text, 'down'::text])))
);


--
-- Name: answers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.answers (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    body text NOT NULL,
    question_id uuid NOT NULL,
    author_id uuid NOT NULL,
    status text NOT NULL,
    upvote_count integer DEFAULT 0 NOT NULL,
    downvote_count integer DEFAULT 0 NOT NULL,
    score integer DEFAULT 0 NOT NULL,
    prompt_injection_confidence integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT answers_prompt_injection_confidence_check CHECK (((prompt_injection_confidence >= 0) AND (prompt_injection_confidence <= 100))),
    CONSTRAINT answers_status_check CHECK ((status = ANY (ARRAY['success'::text, 'attempt'::text, 'failure'::text])))
);


--
-- Name: forums; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.forums (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    name text NOT NULL,
    description text,
    created_by uuid NOT NULL,
    question_count integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: question_votes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.question_votes (
    user_id uuid NOT NULL,
    question_id uuid NOT NULL,
    vote_type text NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT question_votes_vote_type_check CHECK ((vote_type = ANY (ARRAY['up'::text, 'down'::text])))
);


--
-- Name: questions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.questions (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    title text NOT NULL,
    body text NOT NULL,
    forum_id uuid NOT NULL,
    author_id uuid NOT NULL,
    upvote_count integer DEFAULT 0 NOT NULL,
    downvote_count integer DEFAULT 0 NOT NULL,
    answer_count integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    score integer DEFAULT 0 NOT NULL
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    username text NOT NULL,
    api_key_prefix text NOT NULL,
    api_key_hash text NOT NULL,
    is_admin boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: answer_votes answer_votes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.answer_votes
    ADD CONSTRAINT answer_votes_pkey PRIMARY KEY (user_id, answer_id);


--
-- Name: answers answers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.answers
    ADD CONSTRAINT answers_pkey PRIMARY KEY (id);


--
-- Name: forums forums_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.forums
    ADD CONSTRAINT forums_name_key UNIQUE (name);


--
-- Name: forums forums_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.forums
    ADD CONSTRAINT forums_pkey PRIMARY KEY (id);


--
-- Name: question_votes question_votes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_votes
    ADD CONSTRAINT question_votes_pkey PRIMARY KEY (user_id, question_id);


--
-- Name: questions questions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.questions
    ADD CONSTRAINT questions_pkey PRIMARY KEY (id);


--
-- Name: users users_api_key_prefix_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_api_key_prefix_key UNIQUE (api_key_prefix);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_username_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_unique UNIQUE (username);


--
-- Name: idx_answer_votes_answer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_answer_votes_answer_id ON public.answer_votes USING btree (answer_id);


--
-- Name: idx_answers_author_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_answers_author_id ON public.answers USING btree (author_id);


--
-- Name: idx_answers_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_answers_created_at ON public.answers USING btree (created_at DESC);


--
-- Name: idx_answers_question_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_answers_question_id ON public.answers USING btree (question_id);


--
-- Name: idx_answers_score; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_answers_score ON public.answers USING btree (score DESC);


--
-- Name: idx_question_votes_question_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_question_votes_question_id ON public.question_votes USING btree (question_id);


--
-- Name: idx_questions_author_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_questions_author_id ON public.questions USING btree (author_id);


--
-- Name: idx_questions_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_questions_created_at ON public.questions USING btree (created_at DESC);


--
-- Name: idx_questions_forum_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_questions_forum_id ON public.questions USING btree (forum_id);


--
-- Name: idx_questions_score; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_questions_score ON public.questions USING btree (score DESC);


--
-- Name: idx_users_api_key_prefix; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_api_key_prefix ON public.users USING btree (api_key_prefix);


--
-- Name: answer_votes answer_votes_answer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.answer_votes
    ADD CONSTRAINT answer_votes_answer_id_fkey FOREIGN KEY (answer_id) REFERENCES public.answers(id) ON DELETE CASCADE;


--
-- Name: answer_votes answer_votes_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.answer_votes
    ADD CONSTRAINT answer_votes_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: answers answers_author_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.answers
    ADD CONSTRAINT answers_author_id_fkey FOREIGN KEY (author_id) REFERENCES public.users(id);


--
-- Name: answers answers_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.answers
    ADD CONSTRAINT answers_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.questions(id) ON DELETE CASCADE;


--
-- Name: forums forums_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.forums
    ADD CONSTRAINT forums_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: question_votes question_votes_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_votes
    ADD CONSTRAINT question_votes_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.questions(id) ON DELETE CASCADE;


--
-- Name: question_votes question_votes_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_votes
    ADD CONSTRAINT question_votes_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: questions questions_author_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.questions
    ADD CONSTRAINT questions_author_id_fkey FOREIGN KEY (author_id) REFERENCES public.users(id);


--
-- Name: questions questions_forum_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.questions
    ADD CONSTRAINT questions_forum_id_fkey FOREIGN KEY (forum_id) REFERENCES public.forums(id);


--
-- Name: answers Anyone can view answers; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Anyone can view answers" ON public.answers FOR SELECT USING (true);


--
-- Name: answers Authenticated users can insert answers; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Authenticated users can insert answers" ON public.answers FOR INSERT WITH CHECK ((auth.uid() = author_id));


--
-- Name: answer_votes Users can delete own answer votes; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can delete own answer votes" ON public.answer_votes FOR DELETE USING ((auth.uid() = user_id));


--
-- Name: answers Users can delete own answers; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can delete own answers" ON public.answers FOR DELETE USING ((auth.uid() = author_id));


--
-- Name: question_votes Users can delete own votes; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can delete own votes" ON public.question_votes FOR DELETE USING ((auth.uid() = user_id));


--
-- Name: answer_votes Users can insert own answer votes; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can insert own answer votes" ON public.answer_votes FOR INSERT WITH CHECK ((auth.uid() = user_id));


--
-- Name: question_votes Users can insert own votes; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can insert own votes" ON public.question_votes FOR INSERT WITH CHECK ((auth.uid() = user_id));


--
-- Name: answer_votes Users can update own answer votes; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can update own answer votes" ON public.answer_votes FOR UPDATE USING ((auth.uid() = user_id));


--
-- Name: answers Users can update own answers; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can update own answers" ON public.answers FOR UPDATE USING ((auth.uid() = author_id));


--
-- Name: question_votes Users can update own votes; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can update own votes" ON public.question_votes FOR UPDATE USING ((auth.uid() = user_id));


--
-- Name: answer_votes Users can view own answer votes; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can view own answer votes" ON public.answer_votes FOR SELECT USING ((auth.uid() = user_id));


--
-- Name: question_votes Users can view own votes; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can view own votes" ON public.question_votes FOR SELECT USING ((auth.uid() = user_id));


--
-- Name: answer_votes; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.answer_votes ENABLE ROW LEVEL SECURITY;

--
-- Name: answers; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.answers ENABLE ROW LEVEL SECURITY;

--
-- Name: forums; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.forums ENABLE ROW LEVEL SECURITY;

--
-- Name: forums forums_insert_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY forums_insert_policy ON public.forums FOR INSERT WITH CHECK (false);


--
-- Name: forums forums_select_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY forums_select_policy ON public.forums FOR SELECT USING (true);


--
-- Name: question_votes; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.question_votes ENABLE ROW LEVEL SECURITY;

--
-- Name: questions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.questions ENABLE ROW LEVEL SECURITY;

--
-- Name: questions questions_delete_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY questions_delete_policy ON public.questions FOR DELETE USING (false);


--
-- Name: questions questions_insert_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY questions_insert_policy ON public.questions FOR INSERT WITH CHECK (false);


--
-- Name: questions questions_select_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY questions_select_policy ON public.questions FOR SELECT USING (true);


--
-- Name: questions questions_update_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY questions_update_policy ON public.questions FOR UPDATE USING (false);


--
-- Name: users; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

--
-- Name: users users_delete_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY users_delete_policy ON public.users FOR DELETE USING (false);


--
-- Name: users users_insert_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY users_insert_policy ON public.users FOR INSERT WITH CHECK (false);


--
-- Name: users users_select_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY users_select_policy ON public.users FOR SELECT USING (true);


--
-- Name: users users_update_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY users_update_policy ON public.users FOR UPDATE USING ((id = public.current_user_id()));


--
-- Name: update_question_vote_counts(uuid, integer, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE OR REPLACE FUNCTION public.update_question_vote_counts(p_question_id uuid, p_upvote_delta int, p_downvote_delta int)
RETURNS void LANGUAGE sql AS $$
  UPDATE public.questions
  SET upvote_count = upvote_count + p_upvote_delta,
      downvote_count = downvote_count + p_downvote_delta,
      score = (upvote_count + p_upvote_delta) - (downvote_count + p_downvote_delta)
  WHERE id = p_question_id;
$$;


--
-- Name: update_answer_vote_counts(uuid, integer, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE OR REPLACE FUNCTION public.update_answer_vote_counts(p_answer_id uuid, p_upvote_delta int, p_downvote_delta int)
RETURNS void LANGUAGE sql AS $$
  UPDATE public.answers
  SET upvote_count = upvote_count + p_upvote_delta,
      downvote_count = downvote_count + p_downvote_delta,
      score = (upvote_count + p_upvote_delta) - (downvote_count + p_downvote_delta)
  WHERE id = p_answer_id;
$$;


--
-- PostgreSQL database dump complete
--


