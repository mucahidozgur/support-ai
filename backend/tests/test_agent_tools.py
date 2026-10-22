"""Uzman tool yolları (summarize / extract_actions / compare) testleri."""

import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.agent.nodes import router_node

DOCS_URL = "/api/documents"
AGENT_URL = "/api/ai/agent"

MOCK_ANSWER = "Araç yanıtı."

# Smoketest'te "Python nedir?" sorgusuyla benzerlik 0.72 ölçüldü (MIN_SIMILARITY=0.55).
PYTHON_TEXT = """Python yuksek seviyeli bir programlama dilidir. Guido van Rossum
tarafindan gelistirilmistir. Dinamik tiplidir ve okunabilirligi yuksektir. Yapay zeka,
veri bilimi ve web gelistirmede yaygin kullanilir."""

JS_TEXT = """JavaScript web tarayicilarinda calisan bir betik dilidir. Brendan Eich
tarafindan 1995 yilinda gelistirilmistir. Dinamik tiplidir ve oncelikle istemci
tarafinda etkilesimli arayuzler olusturmak icin kullanilir."""


def _patch_llm(monkeypatch: pytest.MonkeyPatch, intent: str, answer: str = MOCK_ANSWER) -> None:
    """Router ve yanıt akışının LLM'ini FakeListChatModel ile değiştirir.

    responses[0] router tarafından tüketilir, responses[1] tool yanıtının
    stream'i için kullanılır.
    """
    fake = FakeListChatModel(responses=[intent, answer])
    monkeypatch.setattr("app.agent.nodes.get_llm", lambda: fake)
    monkeypatch.setattr("app.services.agent.get_llm", lambda: fake)


def _create_and_index(
    app_client: TestClient, headers: dict[str, str], title: str, content: str
) -> dict:
    """Yardımcı: doküman oluşturup index'ler, doküman body'sini döndürür."""
    created = app_client.post(DOCS_URL, json={"title": title, "content": content}, headers=headers)
    assert created.status_code == 201
    doc = created.json()
    indexed = app_client.post(f"{DOCS_URL}/{doc['id']}/index", headers=headers)
    assert indexed.status_code == 200
    return doc


def _collect_events(
    app_client: TestClient, payload: dict[str, object], headers: dict[str, str]
) -> list[tuple[str, object]]:
    """SSE stream'ini tamamen tüketir ve (event, data) çiftlerini döndürür."""
    with app_client.stream("POST", AGENT_URL, json=payload, headers=headers) as resp:
        assert resp.status_code == 200
        raw = resp.read().decode("utf-8")
    events: list[tuple[str, object]] = []
    current_event: str | None = None
    data_lines: list[str] = []
    for line in raw.split("\n"):
        line = line.rstrip("\r")
        if line == "":
            if current_event is not None:
                events.append((current_event, json.loads("\n".join(data_lines))))
                current_event = None
                data_lines = []
        elif line.startswith("event: "):
            current_event = line[len("event: ") :]
        elif line.startswith("data: "):
            data_lines.append(line[len("data: ") :])
    return events


def _event_names(events: list[tuple[str, object]]) -> list[str]:
    """Event çiftlerinden yalnızca event adlarını çıkarır."""
    return [name for name, _ in events]


def _data_of(events: list[tuple[str, object]], name: str) -> object:
    """Adı verilen ilk event'in data'sını döndürür."""
    return events[_event_names(events).index(name)][1]


def _assert_tool_stream_shape(
    events: list[tuple[str, object]],
    intent: str,
    expected_source_doc_ids: set[str],
) -> None:
    """Tool stream'lerinin ortak şeklini doğrular: intent + sources + token + done."""
    names = _event_names(events)
    assert names[0] == "intent"
    assert _data_of(events, "intent")["intent"] == intent
    assert "sources" in names
    assert "token" in names
    assert "done" in names

    sources = _data_of(events, "sources")
    assert isinstance(sources, list) and len(sources) >= 1
    for source in sources:
        assert "content" not in source  # sources metadata taşır, içerik değil
        assert source["similarity"] > 0
    assert {source["document_id"] for source in sources} == expected_source_doc_ids

    tokens = "".join(data["text"] for name, data in events if name == "token")
    assert tokens == MOCK_ANSWER
    assert _data_of(events, "done")["finish_reason"] == "stop"


async def test_router_summarize(monkeypatch: pytest.MonkeyPatch) -> None:
    """ "bu dokümanı özetle" sorgusu summarize olarak sınıflandırılır."""
    _patch_llm(monkeypatch, "summarize")
    result = await router_node({"query": "bu dokümanı özetle"})
    assert result["intent"] == "summarize"


async def test_router_extract_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    """ "yapılacakları çıkar" sorgusu extract_actions olarak sınıflandırılır."""
    _patch_llm(monkeypatch, "extract_actions")
    result = await router_node({"query": "yapılacakları çıkar"})
    assert result["intent"] == "extract_actions"


async def test_router_compare(monkeypatch: pytest.MonkeyPatch) -> None:
    """ "A ile B'yi karşılaştır" sorgusu compare olarak sınıflandırılır."""
    _patch_llm(monkeypatch, "compare")
    result = await router_node({"query": "A ile B'yi karşılaştır"})
    assert result["intent"] == "compare"


def test_summarize_stream(
    app_client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """summarize yolu: seçilen dokümanın tüm chunk'ları üzerinden özet stream'i."""
    _patch_llm(monkeypatch, "summarize")
    doc1 = _create_and_index(app_client, auth_headers, "Python Notlari", PYTHON_TEXT)
    _create_and_index(app_client, auth_headers, "JS Notlari", JS_TEXT)  # seçilmemeli
    events = _collect_events(
        app_client,
        {"query": "bu dokümanı özetle", "document_ids": [doc1["id"]]},
        auth_headers,
    )
    _assert_tool_stream_shape(events, "summarize", {doc1["id"]})


def test_extract_actions_stream(
    app_client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """extract_actions yolu: seçilen doküman üzerinden aksiyon stream'i."""
    _patch_llm(monkeypatch, "extract_actions")
    doc1 = _create_and_index(app_client, auth_headers, "Toplanti Notlari", PYTHON_TEXT)
    events = _collect_events(
        app_client,
        {"query": "yapılacakları çıkar", "document_ids": [doc1["id"]]},
        auth_headers,
    )
    _assert_tool_stream_shape(events, "extract_actions", {doc1["id"]})


def test_compare_stream(
    app_client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """compare yolu: iki dokümanın tüm chunk'ları üzerinden karşılaştırma stream'i."""
    _patch_llm(monkeypatch, "compare")
    doc1 = _create_and_index(app_client, auth_headers, "Python Notlari", PYTHON_TEXT)
    doc2 = _create_and_index(app_client, auth_headers, "JS Notlari", JS_TEXT)
    events = _collect_events(
        app_client,
        {
            "query": "A ile B'yi karşılaştır",
            "document_ids": [doc1["id"], doc2["id"]],
        },
        auth_headers,
    )
    _assert_tool_stream_shape(events, "compare", {doc1["id"], doc2["id"]})


def test_compare_with_one_document(
    app_client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """compare için tek doküman seçilirse error event'i döner."""
    _patch_llm(monkeypatch, "compare")
    doc1 = _create_and_index(app_client, auth_headers, "Python Notlari", PYTHON_TEXT)
    events = _collect_events(
        app_client,
        {"query": "A ile B'yi karşılaştır", "document_ids": [doc1["id"]]},
        auth_headers,
    )
    names = _event_names(events)
    assert names[0] == "intent"
    assert _data_of(events, "intent")["intent"] == "compare"
    assert "token" not in names
    assert _data_of(events, "error")["message"] == "Karşılaştırma için en az 2 doküman seçmelisiniz"
    assert _data_of(events, "done")["finish_reason"] == "error"


def test_summarize_no_documents(
    app_client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Doküman seçilmezse summarize error event'i döner."""
    _patch_llm(monkeypatch, "summarize")
    events = _collect_events(app_client, {"query": "bu dokümanı özetle"}, auth_headers)
    names = _event_names(events)
    assert names[0] == "intent"
    assert _data_of(events, "intent")["intent"] == "summarize"
    assert "token" not in names
    assert _data_of(events, "error")["message"] == "Özetlemek için doküman bulunamadı"
    assert _data_of(events, "done")["finish_reason"] == "error"


def test_agent_still_handles_qa(
    app_client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regresyon: qa yolu Faz 4b-ii değişikliklerinden sonra hâlâ çalışıyor."""
    _patch_llm(monkeypatch, "qa", "Python yanıtı.")
    _create_and_index(app_client, auth_headers, "Python Notlari", PYTHON_TEXT)
    events = _collect_events(app_client, {"query": "Python nedir?"}, auth_headers)
    names = _event_names(events)
    assert names[0] == "intent"
    assert _data_of(events, "intent")["intent"] == "qa"
    assert "sources" in names
    assert "token" in names
    tokens = "".join(data["text"] for name, data in events if name == "token")
    assert tokens == "Python yanıtı."
    assert _data_of(events, "done")["finish_reason"] == "stop"
