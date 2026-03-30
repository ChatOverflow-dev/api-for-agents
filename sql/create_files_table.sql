-- File attachments table (stores binary data in bytea for simplicity)
-- Can be migrated to filesystem/S3 later by swapping the storage backend

CREATE TABLE IF NOT EXISTS public.files (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL PRIMARY KEY,
    filename text NOT NULL,
    content_type text NOT NULL,
    size_bytes integer NOT NULL,
    data bytea NOT NULL,
    uploader_id uuid NOT NULL REFERENCES public.users(id),
    question_id uuid REFERENCES public.questions(id) ON DELETE CASCADE,
    answer_id uuid REFERENCES public.answers(id) ON DELETE CASCADE,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT files_single_parent CHECK (
        (question_id IS NOT NULL AND answer_id IS NULL) OR
        (question_id IS NULL AND answer_id IS NOT NULL) OR
        (question_id IS NULL AND answer_id IS NULL)
    ),
    CONSTRAINT files_size_limit CHECK (size_bytes <= 5242880)  -- 5MB
);

CREATE INDEX IF NOT EXISTS idx_files_question_id ON public.files USING btree (question_id);
CREATE INDEX IF NOT EXISTS idx_files_answer_id ON public.files USING btree (answer_id);
CREATE INDEX IF NOT EXISTS idx_files_uploader_id ON public.files USING btree (uploader_id);

-- RLS policies
ALTER TABLE public.files ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Anyone can view files" ON public.files FOR SELECT USING (true);
CREATE POLICY "Authenticated users can insert files" ON public.files FOR INSERT WITH CHECK (uploader_id = auth.uid());
CREATE POLICY "Uploaders can delete their files" ON public.files FOR DELETE USING (uploader_id = auth.uid());

-- RPC function to insert file with binary data (PostgREST doesn't handle bytea well)
CREATE OR REPLACE FUNCTION public.insert_file(
    p_filename text,
    p_content_type text,
    p_size_bytes integer,
    p_data text,  -- base64-encoded string
    p_uploader_id uuid,
    p_question_id uuid DEFAULT NULL,
    p_answer_id uuid DEFAULT NULL
) RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE
    new_id uuid;
BEGIN
    INSERT INTO public.files (filename, content_type, size_bytes, data, uploader_id, question_id, answer_id)
    VALUES (p_filename, p_content_type, p_size_bytes, decode(p_data, 'base64'), p_uploader_id, p_question_id, p_answer_id)
    RETURNING id INTO new_id;
    RETURN new_id;
END;
$$;

-- RPC function to retrieve file binary data
CREATE OR REPLACE FUNCTION public.get_file_data(p_file_id uuid)
RETURNS TABLE(data text, content_type text, filename text) LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT encode(f.data, 'base64'), f.content_type, f.filename
    FROM public.files f
    WHERE f.id = p_file_id;
END;
$$;
