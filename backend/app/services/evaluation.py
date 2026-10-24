"""RAGAS değerlendirme servisi: sentetik test seti üretimi + metrik hesaplama.

Gerçek LLM (Groq) ve RAGAS çağrıları yapılır. Testler bu modülün `get_llm`
ve `_run_ragas` sembollerini mock'lar; gerçek model çağrısı yapılmaz.
"""

import json
import logging
import re
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import get_llm
from app.models.document import Document
from app.services.prompts import SYSTEM_PROMPT, build_context_block, build_user_prompt
from app.services.rag import RAGService

logger = logging.getLogger(__name__)

TEST_SET_SYSTEM = (
    "Sen bir RAG değerlendirme verisi üreticisisin. Verilen dokümana dayanarak, "
    "cevabı YALNIZCA dokümanda bulunan sorular üretirsin. Uydurmazsın."
)

NO_CONTEXT_ANSWER = "Bu bilgi knowledge base'de bulunmuyor."


class EvaluationError(Exception):
    """LLM/ürün kaynaklı değerlendirme hatası (istemci girdi hatası değil)."""


async def _get_owned_document(
    db: AsyncSession, owner_id: UUID, document_id: UUID
) -> Document | None:
    """Dokümanı owner filtresiyle getirir."""
    stmt = select(Document).where(Document.id == document_id, Document.owner_id == owner_id)
    return await db.scalar(stmt)


async def generate_test_set(
    db: AsyncSession, owner_id: UUID, document_id: UUID, num_questions: int = 5
) -> list[dict] | None:
    """Dokümandan LLM ile sentetik soru-cevap seti üretir.

    Doküman owner'a ait değilse None döner (endpoint 404'e çevirir).
    LLM çağrısı hatasında EvaluationError, çıktı çözülemezse ValueError fırlatır.
    """
    doc = await _get_owned_document(db, owner_id, document_id)
    if doc is None:
        return None

    prompt = (
        f"Aşağıdaki dokümana dayanarak {num_questions} adet soru ve doğru cevap üret. "
        "Sorular dokümandaki bilgilerle cevaplanabilir olmalı; cevabı dokümanda "
        "olmayan soru üretme. Yalnızca şu formatta JSON dön:\n"
        '[{"question": "...", "ground_truth": "..."}]\n\n'
        f"DOKÜMAN:\n{doc.content}"
    )
    try:
        response = get_llm().invoke([SystemMessage(TEST_SET_SYSTEM), HumanMessage(prompt)])
    except Exception as exc:
        logger.exception("Test seti üretimi LLM hatası")
        raise EvaluationError(f"LLM test seti üretimi başarısız: {exc}") from exc
    return _parse_test_set(getattr(response, "content", str(response)))


def _parse_test_set(raw: str) -> list[dict]:
    """LLM çıktısını JSON'a çevirir; ```json bloklarını ve sarmalayıcıları ayıklar."""
    text = raw.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if not match:
            raise ValueError("LLM çıktısı JSON olarak çözülemedi") from None
        data = json.loads(match.group(1))
    if isinstance(data, dict):
        # LLM bazen {"questions": [...]} gibi sarmalayıcı anahtar kullanır.
        data = data.get("questions") or data.get("test_set") or data.get("items") or []
    if not isinstance(data, list):
        # Bu, çağıranın argüman tipi değil; LLM çıktısının formatı olduğu için
        # ValueError doğru seçimdir (TRY004 bu bağlamda geçerli değil).
        raise ValueError("LLM çıktısı liste değil")  # noqa: TRY004
    items: list[dict] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        question = str(entry.get("question", "")).strip()
        ground_truth = str(entry.get("ground_truth", entry.get("answer", ""))).strip()
        if question:
            items.append({"question": question, "ground_truth": ground_truth})
    if not items:
        raise ValueError("Üretilen test seti boş")
    return items


def _generate_answer(llm, question: str, contexts: list[str]) -> str:
    """Context'lerden LLM ile cevap üretir; context yoksa bilinmeyen yanıtı döner."""
    if not contexts:
        return NO_CONTEXT_ANSWER
    context_block = build_context_block(
        [
            {"document_title": f"ctx{i}", "chunk_index": i, "content": content}
            for i, content in enumerate(contexts)
        ]
    )
    messages = [
        SystemMessage(SYSTEM_PROMPT),
        HumanMessage(build_user_prompt(question, context_block)),
    ]
    response = llm.invoke(messages)
    return getattr(response, "content", str(response))


async def evaluate_rag(questions: list[dict], rag_service: RAGService) -> dict:
    """Test setini RAGAS metrikleriyle değerlendirir.

    Her soru için akış: hybrid+rerank arama → context'ler → LLM cevabı → RAGAS.
    Dönen dict anahtarları: faithfulness, answer_relevancy, context_precision.
    """
    if not questions:
        raise ValueError("test_set boş olamaz")
    llm = get_llm()
    samples: list[dict] = []
    for item in questions:
        question = item["question"]
        chunks = await rag_service.search_hybrid_rerank(query=question, limit=3)
        contexts = [c["content"] for c in chunks]
        answer = _generate_answer(llm, question, contexts)
        samples.append(
            {
                "question": question,
                "contexts": contexts,
                "answer": answer,
                "ground_truth": item.get("ground_truth", ""),
            }
        )
    return _run_ragas(samples)


def _run_ragas(samples: list[dict]) -> dict:
    """RAGAS evaluate ile üç metriği hesaplar.

    ragas ağır bir bağımlılıktır; yalnızca değerlendirme çağrıldığında import
    edilir (app import'unu yavaşlatmasın). Groq LLM'i LangchainLLMWrapper ile
    bağlanır; bu üç metrik LLM tabanlıdır, embedding gerektirmez.
    """
    from ragas import evaluate  # ağır import: yalnızca gerektiğinde
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics.collections.answer_relevancy import AnswerRelevancy
    from ragas.metrics.collections.context_precision import ContextPrecision
    from ragas.metrics.collections.faithfulness import Faithfulness

    result = evaluate(
        dataset=samples,
        metrics=[Faithfulness(), AnswerRelevancy(), ContextPrecision()],
        llm=LangchainLLMWrapper(get_llm()),
    )
    return {
        "faithfulness": float(result["faithfulness"]),
        "answer_relevancy": float(result["answer_relevancy"]),
        "context_precision": float(result["context_precision"]),
    }
