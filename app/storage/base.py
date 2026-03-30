from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class StoredFile:
    id: str
    filename: str
    content_type: str
    size_bytes: int
    url: str


@dataclass
class FileData:
    content: bytes
    content_type: str
    filename: str


class FileStorage(ABC):
    @abstractmethod
    def upload(
        self,
        filename: str,
        content_type: str,
        data: bytes,
        uploader_id: str,
        question_id: str | None = None,
        answer_id: str | None = None,
    ) -> StoredFile: ...

    @abstractmethod
    def get_data(self, file_id: str) -> FileData | None: ...

    @abstractmethod
    def get_metadata(self, file_id: str) -> StoredFile | None: ...

    @abstractmethod
    def list_for_question(self, question_id: str) -> list[StoredFile]: ...

    @abstractmethod
    def list_for_answer(self, answer_id: str) -> list[StoredFile]: ...

    @abstractmethod
    def list_for_questions(self, question_ids: list[str]) -> dict[str, list[StoredFile]]: ...

    @abstractmethod
    def list_for_answers(self, answer_ids: list[str]) -> dict[str, list[StoredFile]]: ...

    @abstractmethod
    def delete(self, file_id: str) -> bool: ...
