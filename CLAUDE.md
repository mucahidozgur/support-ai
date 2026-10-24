# CLAUDE.md — Support AI

## Project identity
Enterprise RAG assistant for **SupportHub** (B2B SaaS, customer support platform).
Built as a real client delivery (Upwork job simulation: "AI/ML Engineer — LLMs, RAG, AI Agents").

## THE non-negotiable requirement
**Citation zorunlu, hallucination kabul edilemez.** Every answer MUST cite
(document ID + chunk ID + similarity score). If retrieval confidence is below
threshold, respond: "Bu bilgi knowledge base'de bulunmuyor." Never invent.

The client's words: "bir yanlış cevap bize müşteri kaybettiriyor."

## Client
SupportHub — see `docs/CLIENT_BRIEF.md` for full brief.
- 5.000+ KB articles
- Support agents spend 30% of time searching for answers
- Enterprise customers, zero tolerance for wrong answers

## Deliverables (contracted)
1. RAG chat with verifiable citations
2. Ticket summarization
3. Suggested response generation for agents
4. Evaluation dashboard (RAGAS metrics)
5. Observability (Langfuse trace)

## Stack
- **Backend:** Python 3.11, FastAPI, SQLAlchemy 2.0 async, Alembic, Pydantic v2
- **AI:** LangGraph, LangChain, Groq (qwen-3.8-27b), sentence-transformers (bge-small)
- **Vector DB:** PostgreSQL 16 + pgvector
- **Frontend:** Next.js 14 App Router, TypeScript, Tailwind, Zustand
- **Infra:** Docker Compose (postgres + api + web)
- **New additions (this project):** BM25 (PostgreSQL FTS: tsvector/websearch_to_tsquery/ts_rank),
  cross-encoder (bge-reranker-v2-m3), RAGAS, Langfuse, unstructured

## Architecture
See `docs/ARCHITECTURE.md` (will be created in Faz 9).
For now: base is docuflow-ai fork. Ports below.

## Ports & services
| Service | Port | Container |
|---------|------|-----------|
| web | 3002 | support-web |
| api | 8002 | support-api |
| postgres | 5434 | support-postgres |

(docuflow 3000/8000/5432, mizan 3001/8001/5433 — no conflicts)

## Current state
**Faz 0-5 done:** Forked from docuflow-ai, rebranded to Support AI, ports 5434/8002/3002,
own DB (support/support_test) + Docker Compose stack running. Hybrid search live:
`POST /api/ai/search/hybrid` (vector + BM25/FTS + RRF, alpha ağırlıklı) + cross-encoder
rerank (bge-reranker-v2-m3, lazy singleton, use_rerank default True) + hiyerarşik
chunking (Markdown başlıkları → heading kolonu) + parent retrieval (expand_context).
RAGAS değerlendirmesi: `POST /api/ai/evaluate/generate-set` + `/api/ai/evaluate/run`
+ CLI `scripts/run_evaluation.py`. Chat: hybrid+rerank → güven eşiği (0.55) → LLM →
citation doğrulaması + hallucination skoru (verification SSE event'i; verify=False
ile kapatılabilir). Yetersiz context'te LLM çağrılmaz, sabit "bilgi yok" cevabı döner.
Not: langchain-community 0.3.31'e pin'li (0.4.x ragas 0.4.3 ile uyumsuz).
Host dev venv: `backend/.venv` (Python 3.13; Docker image uses 3.11).
Next: Faz 6 (Langfuse observability).

## Roadmap
- [x] Faz 0: Fork base + port + branding
- [x] Faz 1: Hybrid search (BM25 + vector + RRF)
- [x] Faz 2: Cross-encoder reranking
- [x] Faz 3: Semantic + hierarchical chunking
- [x] Faz 4: RAGAS evaluation + synthetic test set
- [x] Faz 5: Citation verification + hallucination detector
- [ ] Faz 6: Langfuse observability
- [ ] Faz 7: Self-critique / corrective RAG agent
- [ ] Faz 8: Admin analytics dashboard
- [ ] Faz 9: Docs + demo + case study

## Code rules
- Type hints required everywhere
- `black` + `ruff` (line-length 100), 0 warnings
- Every new endpoint: ≥1 pytest (happy path + 1 error)
- Never hardcode secrets — .env only
- Conventional commits (feat/fix/refactor/test/docs/chore)
- No new dependency without justification in the commit message

## Testing
- `cd backend && pytest -v` — currently 86 tests passing
- After each phase: must remain ≥47 passing + add new tests
- DB isolation: tests use `support_test` DB, never touch `support` DB

## Deploy targets (future)
- Backend: Render free tier (Docker)
- DB: Neon (pgvector)
- Frontend: Vercel
- (Same pattern as docuflow-ai — reuse `.github/workflows/keepalive.yml`)