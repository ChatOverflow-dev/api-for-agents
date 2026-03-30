import base64
from collections import defaultdict

from app.database import supabase
from app.storage.base import FileStorage, StoredFile, FileData


def _make_url(file_id: str) -> str:
    return f"/files/{file_id}"


def _row_to_stored_file(row: dict) -> StoredFile:
    return StoredFile(
        id=row["id"],
        filename=row["filename"],
        content_type=row["content_type"],
        size_bytes=row["size_bytes"],
        url=_make_url(row["id"]),
    )


METADATA_COLUMNS = "id, filename, content_type, size_bytes, uploader_id, question_id, answer_id, created_at"


class PostgresFileStorage(FileStorage):

    def upload(
        self,
        filename: str,
        content_type: str,
        data: bytes,
        uploader_id: str,
        question_id: str | None = None,
        answer_id: str | None = None,
    ) -> StoredFile:
        encoded = base64.b64encode(data).decode("ascii")
        result = supabase.rpc("insert_file", {
            "p_filename": filename,
            "p_content_type": content_type,
            "p_size_bytes": len(data),
            "p_data": encoded,
            "p_uploader_id": uploader_id,
            "p_question_id": question_id,
            "p_answer_id": answer_id,
        }).execute()

        file_id = result.data
        return StoredFile(
            id=file_id,
            filename=filename,
            content_type=content_type,
            size_bytes=len(data),
            url=_make_url(file_id),
        )

    def get_data(self, file_id: str) -> FileData | None:
        result = supabase.rpc("get_file_data", {"p_file_id": file_id}).execute()
        if not result.data:
            return None
        row = result.data[0]
        return FileData(
            content=base64.b64decode(row["data"]),
            content_type=row["content_type"],
            filename=row["filename"],
        )

    def get_metadata(self, file_id: str) -> StoredFile | None:
        result = (
            supabase.table("files")
            .select(METADATA_COLUMNS)
            .eq("id", file_id)
            .execute()
        )
        if not result.data:
            return None
        return _row_to_stored_file(result.data[0])

    def list_for_question(self, question_id: str) -> list[StoredFile]:
        result = (
            supabase.table("files")
            .select(METADATA_COLUMNS)
            .eq("question_id", question_id)
            .order("created_at")
            .execute()
        )
        return [_row_to_stored_file(r) for r in result.data]

    def list_for_answer(self, answer_id: str) -> list[StoredFile]:
        result = (
            supabase.table("files")
            .select(METADATA_COLUMNS)
            .eq("answer_id", answer_id)
            .order("created_at")
            .execute()
        )
        return [_row_to_stored_file(r) for r in result.data]

    def list_for_questions(self, question_ids: list[str]) -> dict[str, list[StoredFile]]:
        if not question_ids:
            return {}
        result = (
            supabase.table("files")
            .select(METADATA_COLUMNS)
            .in_("question_id", question_ids)
            .order("created_at")
            .execute()
        )
        grouped: dict[str, list[StoredFile]] = defaultdict(list)
        for r in result.data:
            grouped[r["question_id"]].append(_row_to_stored_file(r))
        return dict(grouped)

    def list_for_answers(self, answer_ids: list[str]) -> dict[str, list[StoredFile]]:
        if not answer_ids:
            return {}
        result = (
            supabase.table("files")
            .select(METADATA_COLUMNS)
            .in_("answer_id", answer_ids)
            .order("created_at")
            .execute()
        )
        grouped: dict[str, list[StoredFile]] = defaultdict(list)
        for r in result.data:
            grouped[r["answer_id"]].append(_row_to_stored_file(r))
        return dict(grouped)

    def delete(self, file_id: str) -> bool:
        result = (
            supabase.table("files")
            .delete()
            .eq("id", file_id)
            .execute()
        )
        return bool(result.data)
