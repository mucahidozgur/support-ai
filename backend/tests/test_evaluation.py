"""RAGAS değerlendirme testleri (LLM ve RAGAS mock'lanır — gerçek çağrı yok)."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.services.evaluation import (
    EvaluationError,
    _parse_test_set,
    evaluate_rag,
    generate_test_set,
)

DOCS_URL = "/api/documents"
GENERATE_URL = "/api/ai/evaluate/generate-set"
RUN_URL = "/api/ai/evaluate/run"


class _FakeLLM:
    """invoke'u önceden belirlenmiş içerikle yanıtlayan sahte chat modeli."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list = []

    def invoke(self, messages, config=None, **kwargs) -> SimpleNamespace:
        self.calls.append(messages)
        return SimpleNamespace(content=self.response)


class _FakeRAG:
    """search_hybrid_rerank'i sabit chunk listesiyle yanıtlayan sahte servis."""

    def __init__(self, chunks: list[dict]) -> None:
        self.chunks = chunks

    async def search_hybrid_rerank(self, query: str, limit: int = 3, **kwargs) -> list[dict]:
        return self.chunks


async def _create_doc(db_session: AsyncSession, owner_id, content: str) -> Document:
    """Doğrudan DB'ye doküman yazar (embedding/index gerekmez)."""
    doc = Document(title="Eval Dokümanı", content=content, owner_id=owner_id)
    db_session.add(doc)
    await db_session.commit()
    return doc


async def test_generate_test_set_format(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LLM JSON çıktısı doğru formatta soru-cevap listesine çevrilir."""
    fake = _FakeLLM(
        json.dumps(
            [
                {"question": "Kurulum nasıl yapılır?", "ground_truth": "Paketleri indirin."},
                {"question": "Hangi port kullanılır?", "ground_truth": "443"},
            ]
        )
    )
    monkeypatch.setattr("app.services.evaluation.get_llm", lambda: fake)
    owner_id = uuid4()
    doc = await _create_doc(db_session, owner_id, "API kurulum rehberi içeriği.")

    questions = await generate_test_set(db_session, owner_id, doc.id, num_questions=2)
    assert questions is not None
    assert len(questions) == 2
    assert all(set(q) == {"question", "ground_truth"} for q in questions)
    assert questions[0]["question"] == "Kurulum nasıl yapılır?"
    # Prompt, doküman içeriğini taşımalı (LLM'e kaynak metin gider).
    prompt_text = str(fake.calls[0][-1].content)
    assert "API kurulum rehberi içeriği." in prompt_text


def test_parse_test_set_handles_fenced_json() -> None:
    """```json blokları içindeki LLM çıktısı da çözülür."""
    items = _parse_test_set('```json\n[{"question": "Q?", "ground_truth": "A"}]\n```')
    assert items == [{"question": "Q?", "ground_truth": "A"}]


def test_parse_test_set_rejects_invalid() -> None:
    """JSON olmayan çıktı ValueError üretir."""
    with pytest.raises(ValueError):
        _parse_test_set("bu bir JSON değil")


async def test_evaluate_rag_empty_input(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Boş test seti ValueError üretir; LLM hiç çağrılmaz."""
    fake = _FakeLLM("")
    monkeypatch.setattr("app.services.evaluation.get_llm", lambda: fake)
    with pytest.raises(ValueError, match="boş olamaz"):
        await evaluate_rag([], _FakeRAG([]))
    assert fake.calls == []


async def test_evaluate_rag_metrics_keys(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dönen dict üç RAGAS metriğini taşır; örnekler RAGAS'a doğru gider."""
    fake_llm = _FakeLLM("Kurulum cevabı.")
    monkeypatch.setattr("app.services.evaluation.get_llm", lambda: fake_llm)

    captured: dict = {}

    def fake_run_ragas(samples: list[dict]) -> dict:
        captured["samples"] = samples
        return {"faithfulness": 0.9, "answer_relevancy": 0.8, "context_precision": 0.75}

    monkeypatch.setattr("app.services.evaluation._run_ragas", fake_run_ragas)
    rag = _FakeRAG([{"content": "ctx-1"}, {"content": "ctx-2"}])

    metrics = await evaluate_rag([{"question": "Kurulum nasıl?", "ground_truth": "Şöyle."}], rag)
    assert set(metrics) == {"faithfulness", "answer_relevancy", "context_precision"}
    assert metrics == {"faithfulness": 0.9, "answer_relevancy": 0.8, "context_precision": 0.75}
    sample = captured["samples"][0]
    assert sample["question"] == "Kurulum nasıl?"
    assert sample["contexts"] == ["ctx-1", "ctx-2"]
    assert sample["answer"] == "Kurulum cevabı."
    assert sample["ground_truth"] == "Şöyle."


def test_generate_set_endpoint(
    app_client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Endpoint: dokümandan sentetik set üretir (200, formatlı)."""
    fake = _FakeLLM(json.dumps([{"question": "Q?", "ground_truth": "A"}]))
    monkeypatch.setattr("app.services.evaluation.get_llm", lambda: fake)
    created = app_client.post(
        DOCS_URL,
        json={"title": "Eval", "content": "Doküman içeriği burada."},
        headers=auth_headers,
    )
    assert created.status_code == 201

    resp = app_client.post(
        GENERATE_URL,
        json={"document_id": created.json()["id"], "num_questions": 1},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["document_id"] == created.json()["id"]
    assert body["questions"] == [{"question": "Q?", "ground_truth": "A"}]


def test_generate_set_endpoint_unknown_doc(
    app_client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Var olmayan doküman → 404; LLM çağrılmaz."""
    fake = _FakeLLM("[]")
    monkeypatch.setattr("app.services.evaluation.get_llm", lambda: fake)
    resp = app_client.post(GENERATE_URL, json={"document_id": str(uuid4())}, headers=auth_headers)
    assert resp.status_code == 404
    assert fake.calls == []


def test_generate_set_endpoint_llm_error(
    app_client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """LLM hatası (EvaluationError) → 502, 500 değil."""

    async def fake_generate(db, owner_id, document_id, num_questions=5):
        raise EvaluationError("LLM çağrısı başarısız")

    monkeypatch.setattr("app.api.ai.generate_test_set", fake_generate)
    resp = app_client.post(GENERATE_URL, json={"document_id": str(uuid4())}, headers=auth_headers)
    assert resp.status_code == 502


def test_evaluate_run_endpoint(
    app_client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Endpoint: RAGAS metriklerini döndürür (200)."""

    async def fake_evaluate(questions: list[dict], rag_service) -> dict:
        return {"faithfulness": 0.91, "answer_relevancy": 0.82, "context_precision": 0.77}

    monkeypatch.setattr("app.api.ai.evaluate_rag", fake_evaluate)
    resp = app_client.post(
        RUN_URL,
        json={"test_set": [{"question": "Q?", "ground_truth": "A"}]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["samples"] == 1
    assert body["metrics"] == {
        "faithfulness": 0.91,
        "answer_relevancy": 0.82,
        "context_precision": 0.77,
    }


def test_evaluate_run_endpoint_empty_set(
    app_client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Boş test seti → 422 (validation)."""
    resp = app_client.post(RUN_URL, json={"test_set": []}, headers=auth_headers)
    assert resp.status_code == 422


def test_evaluate_endpoints_require_auth(app_client: TestClient) -> None:
    """Token'sız değerlendirme istekleri reddedilir."""
    assert app_client.post(GENERATE_URL, json={"document_id": str(uuid4())}).status_code in (
        401,
        403,
    )
    assert app_client.post(RUN_URL, json={"test_set": []}).status_code in (401, 403)
