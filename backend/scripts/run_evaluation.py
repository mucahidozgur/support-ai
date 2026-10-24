"""RAGAS değerlendirme CLI: dokümandan sentetik set üretir ve değerlendirir.

Kullanım (backend/ dizininden):
    python -m scripts.run_evaluation --document-id <uuid> [--num-questions 5]

Gerçek LLM (Groq) çağrısı yapar; .env içinde GROQ_API_KEY dolu olmalı.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv

# Host'tan koşulur; repo kökündeki .env'i elle yükle (conftest ile aynı neden).
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.document import Document
from app.services.evaluation import evaluate_rag, generate_test_set
from app.services.rag import RAGService


async def _run(document_id: str, num_questions: int) -> int:
    """Dokümanı bulur, sentetik set üretir, RAGAS ile değerlendirir."""
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as db:
            doc = await db.scalar(select(Document).where(Document.id == UUID(document_id)))
            if doc is None or doc.owner_id is None:
                print(f"HATA: doküman bulunamadı: {document_id}", file=sys.stderr)
                return 1
            print(f"Doküman: {doc.title} (owner: {doc.owner_id})")

            questions = await generate_test_set(db, doc.owner_id, doc.id, num_questions)
            print(f"\nSentetik test seti ({len(questions)} soru):")
            print(json.dumps(questions, ensure_ascii=False, indent=2))

            metrics = await evaluate_rag(questions, RAGService(db, doc.owner_id))
            print("\nRAGAS metrikleri:")
            print(json.dumps(metrics, ensure_ascii=False, indent=2))
        return 0
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Support AI RAGAS değerlendirmesi")
    parser.add_argument("--document-id", required=True, help="Değerlendirilecek doküman UUID'si")
    parser.add_argument("--num-questions", type=int, default=5, help="Sentetik soru sayısı")
    args = parser.parse_args()
    sys.exit(asyncio.run(_run(args.document_id, args.num_questions)))


if __name__ == "__main__":
    main()
