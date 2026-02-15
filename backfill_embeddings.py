"""
Backfill embeddings for existing questions and answers.

Fetches all rows without embeddings, generates embeddings via the
configured LLM API, and updates the rows in batches.

Usage:
    python backfill_embeddings.py
"""

import httpx
from openai import OpenAI, AzureOpenAI
from supabase import create_client
from app.config import settings

MAX_INPUT_CHARS = 32000
BATCH_SIZE = 50


def main():
    if not settings.llm_api_key:
        print("ERROR: LLM_API_KEY is not set in .env")
        return

    if settings.llm_base_url:
        client = AzureOpenAI(
            api_key=settings.llm_api_key,
            api_version=settings.llm_api_version,
            base_url=f"{settings.llm_base_url}/openai/deployments/{settings.embedding_model}",
            default_headers=settings.llm_default_headers,
            http_client=httpx.Client(verify=False),
        )
    else:
        client = OpenAI(api_key=settings.llm_api_key)

    supabase = create_client(settings.supabase_url, settings.supabase_service_key)

    # --- Backfill questions ---
    print("Fetching questions without embeddings...")
    questions = (
        supabase.table("questions")
        .select("id, title, body")
        .is_("embedding", "null")
        .execute()
    ).data

    print(f"Found {len(questions)} questions to embed.")

    for i in range(0, len(questions), BATCH_SIZE):
        batch = questions[i : i + BATCH_SIZE]
        texts = [(q["title"] + "\n\n" + q["body"])[:MAX_INPUT_CHARS] for q in batch]

        response = client.embeddings.create(input=texts, model=settings.embedding_model)

        for q, emb_data in zip(batch, response.data):
            supabase.table("questions").update(
                {"embedding": emb_data.embedding}
            ).eq("id", q["id"]).execute()

        print(f"  Questions: embedded {min(i + BATCH_SIZE, len(questions))}/{len(questions)}")

    # --- Backfill answers ---
    print("Fetching answers without embeddings...")
    answers = (
        supabase.table("answers")
        .select("id, body")
        .is_("embedding", "null")
        .execute()
    ).data

    print(f"Found {len(answers)} answers to embed.")

    for i in range(0, len(answers), BATCH_SIZE):
        batch = answers[i : i + BATCH_SIZE]
        texts = [a["body"][:MAX_INPUT_CHARS] for a in batch]

        response = client.embeddings.create(input=texts, model=settings.embedding_model)

        for a, emb_data in zip(batch, response.data):
            supabase.table("answers").update(
                {"embedding": emb_data.embedding}
            ).eq("id", a["id"]).execute()

        print(f"  Answers: embedded {min(i + BATCH_SIZE, len(answers))}/{len(answers)}")

    print("Done!")


if __name__ == "__main__":
    main()
