"""Chat (SSE streaming) endpoint testleri."""

import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel

DOCS_URL = "/api/documents"
CHAT_URL = "/api/ai/chat"

MOCK_RESPONSE = "Merhaba dünya."

PYTHON_TEXT = """Python is a high-level, general-purpose programming language. Its design
philosophy emphasizes code readability with the use of significant indentation. Python is
dynamically typed and garbage-collected. It supports multiple programming paradigms,
including structured, object-oriented and functional programming. Python is often described
as a batteries included language due to its comprehensive standard library.

Guido van Rossum began working on Python in the late 1980s as a successor to the ABC
programming language and first released it in 1991 as Python 0.9.0. Python 2.0 was released
in 2000. Python 3.0, released in 2008, was a major revision not completely
backward-compatible with earlier versions. Python 2.7.18, released in 2020, was the last
release of Python 2. Python consistently ranks as one of the most popular programming
languages, and has gained widespread use in the machine learning community.

Python interpreters are available for many operating systems. CPython, the reference
implementation, is developed under a community-driven model. The language provides built-in
types such as lists, dictionaries, sets and tuples. List comprehensions, decorators and
generators are idiomatic features. The standard library includes modules for regular
expressions, networking, file handling and unit testing. Third-party packages are installed
with pip, the package installer for Python.

Python is widely used in web development with frameworks such as Django and FastAPI, in data
science with libraries such as pandas and NumPy, and in machine learning with PyTorch and
scikit-learn. Automated testing with pytest and type checking with mypy are common practices
in professional Python codebases. Asynchronous programming is supported through the asyncio
module, which powers async web frameworks and I/O-bound applications.

The Python community organizes conferences such as PyCon and promotes coding standards
through PEP 8. The language continues to evolve under the stewardship of the Python Software
Foundation. New releases follow a yearly cadence, with performance improvements and new
syntax features in each major version. Developers value Python for its gentle learning
curve, expressive syntax and vast ecosystem of open source packages.
"""


@pytest.fixture
def fake_llm(monkeypatch: pytest.MonkeyPatch) -> FakeListChatModel:
    """ChatService'in LLM'ini FakeListChatModel ile değiştirir (gerçek çağrı yok).

    FakeListChatModel streaming destekler: astream, her yanıtı karakter karakter
    AIMessageChunk olarak üretir (langchain_core kaynağında doğrulandı).
    """
    fake = FakeListChatModel(responses=[MOCK_RESPONSE])
    monkeypatch.setattr("app.services.chat.get_llm", lambda: fake)
    return fake


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
    with app_client.stream("POST", CHAT_URL, json=payload, headers=headers) as resp:
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


def test_chat_no_documents(
    app_client: TestClient, auth_headers: dict[str, str], fake_llm: FakeListChatModel
) -> None:
    """Hiç doküman yokken error + done(no_context) gelir; sources/token gelmez."""
    events = _collect_events(app_client, {"query": "Python nedir?"}, auth_headers)
    names = [name for name, _ in events]
    assert "error" in names
    assert "done" in names
    assert "sources" not in names
    assert "token" not in names
    error_data = events[names.index("error")][1]
    assert error_data["message"] == "Bu soruya cevap verebilecek bir doküman bulunamadı."
    assert events[names.index("done")][1]["finish_reason"] == "no_context"
    assert names[-1] == "done"


def test_chat_with_relevant_document(
    app_client: TestClient, auth_headers: dict[str, str], fake_llm: FakeListChatModel
) -> None:
    """İlgili doküman varken sources → token → done sırasıyla stream edilir."""
    doc = _create_and_index(app_client, auth_headers, "Python Programlama", PYTHON_TEXT)
    events = _collect_events(app_client, {"query": "Python nedir?"}, auth_headers)
    names = [name for name, _ in events]
    assert "sources" in names
    assert "token" in names
    assert "done" in names
    assert names.index("sources") < names.index("token") < names.index("done")

    sources = events[names.index("sources")][1]
    assert isinstance(sources, list)
    assert len(sources) >= 1
    for source in sources:
        assert source["similarity"] > 0
        assert source["document_id"] == doc["id"]
        assert source["document_title"] == "Python Programlama"

    tokens = "".join(data["text"] for name, data in events if name == "token")
    assert tokens == MOCK_RESPONSE
    assert events[names.index("done")][1]["finish_reason"] == "stop"


def test_chat_stream_format(
    app_client: TestClient, auth_headers: dict[str, str], fake_llm: FakeListChatModel
) -> None:
    """Yanıt content-type'ı text/event-stream olmalı."""
    with app_client.stream(
        "POST", CHAT_URL, json={"query": "Python nedir?"}, headers=auth_headers
    ) as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        resp.read()


def test_chat_requires_auth(app_client: TestClient) -> None:
    """Token'sız chat isteği reddedilir."""
    resp = app_client.post(CHAT_URL, json={"query": "Python nedir?"})
    assert resp.status_code in (401, 403)  # HTTPBearer: eski FastAPI 403, yeni 401


def test_chat_llm_init_failure_returns_error_event(
    app_client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM kurulumu patlarsa 500 değil, SSE error + done(error) event'i döner."""

    def boom() -> None:
        raise RuntimeError("simulated LLM init failure")

    monkeypatch.setattr("app.services.chat.get_llm", boom)
    events = _collect_events(app_client, {"query": "Python nedir?"}, auth_headers)
    names = [name for name, _ in events]
    assert "error" in names
    assert "done" in names
    assert "simulated" in events[names.index("error")][1]["message"]
    assert events[names.index("done")][1]["finish_reason"] == "error"
    assert names[-1] == "done"
