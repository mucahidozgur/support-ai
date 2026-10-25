# Support AI

Enterprise RAG assistant for customer support teams.

Built for **SupportHub** (B2B SaaS) — every answer cites its source,
zero tolerance for hallucination.

## The problem we solve

SupportHub's agents spend 30% of their time searching 5,000+ KB articles.
Wrong answers cost enterprise customers. Support AI retrieves the right
answer in seconds — **with proof** (source document + chunk + similarity).

## Features

- 💬 **RAG chat with citations** — her cümle kaynaklı (document + chunk + skor)
- 🔍 **Hybrid search** — BM25 (PostgreSQL FTS) + vektör + Reciprocal Rank Fusion
- 🎯 **Cross-encoder reranking** — bge-reranker-v2-m3, en iyi 3-5 chunk LLM'e gider
- 🧩 **Hierarchical chunking** — Markdown başlıkları + parent retrieval
  (bağlam genişletme)
- 🛡️ **Anti-hallucination** — güven eşiği + citation doğrulama + self-critique +
  sürekli ölçüm (aşağıya bakın)
- ✍️ **Corrective RAG** — yetersiz context'te sorguyu yeniden yazma + cevabı
  eleştirme/düzeltme
- 📋 **Ticket summarization** — özet, aksiyon maddeleri, karşılaştırma (LangGraph)
- 📊 **Evaluation (RAGAS)** — faithfulness, answer_relevancy, context_precision
  + sentetik test seti
- 📈 **Admin analytics dashboard** — KPI kartları, son sorgular, top-10
- 🔭 **Observability (Langfuse)** — her retrieval/rerank/doğrulama adımı trace'li

## Stack

**Backend:** FastAPI, SQLAlchemy 2.0 async, Alembic, LangGraph, LangChain
**AI:** Groq (qwen-3.8-27b), sentence-transformers (bge-small-en-v1.5),
cross-encoder (bge-reranker-v2-m3), RAGAS, Langfuse
**DB:** PostgreSQL 16 + pgvector (+ FTS: tsvector/tsquery)
**Frontend:** Next.js 14 App Router, TypeScript, Tailwind, Zustand
**Infra:** Docker Compose (postgres + api + web)

## Architecture

```
 Frontend (Next.js) ──HTTP/SSE──▶ FastAPI ──▶ Services (rag/chat/critique/
                                        │        verification/evaluation)
                                        ├──▶ LangGraph agent (router)
                                        ├──▶ PostgreSQL 16 + pgvector
                                        │    (documents, chunks, query_logs)
                                        └──▶ Langfuse (trace + feedback)
                                            Groq + yerel modeller
```

Detaylar: [ARCHITECTURE.md](ARCHITECTURE.md)

## Anti-hallucination (4 katman)

1. **Retrieval eşiği:** en iyi skor < 0.55 → LLM çağrılmaz,
   *"Bu bilgi knowledge base'de bulunmuyor."*
2. **Citation verification:** her cümle bir chunk'a bağlanır; uydurma kaynaklar
   reddedilir (SSE `verification` event'i)
3. **Self-critique:** corrective mod sorguyu yeniden yazar, cevabı eleştirir ve
   düzeltir
4. **Sürekli ölçüm:** RAGAS + query_logs analitiği (faithfulness, feedback, latency)

## Quick start

```bash
# 1. Setup
cp .env.example .env
# Edit .env — GROQ_API_KEY zorunlu; LANGFUSE_* opsiyonel (boşsa trace kapalı)

# 2. Build & run
docker compose build api
docker compose up -d postgres api

# 3. Health check
curl http://127.0.0.1:8002/health
# {"status":"ok","service":"support-ai"}

# 4. Frontend (dev)
cd frontend && npm install && npm run dev
# → http://localhost:3002  (login: alice / x)

# 5. Demo verisi (opsiyonel)
docker compose exec api python -m scripts.seed_data
```

## Evaluation (RAGAS)

Hedefler: faithfulness ≥ 0.85, context_precision ≥ 0.75, answer_relevancy ≥ 0.80.

```bash
cd backend
python -m scripts.run_evaluation --document-id <uuid> [--num-questions 5]
```

Detaylar: [docs/EVALUATION.md](docs/EVALUATION.md)

## Testing

```bash
cd backend && pytest -v          # 105 tests
cd frontend && npm run build
```

## Roadmap

- [x] Faz 0: Fork base + port + branding
- [x] Faz 1: Hybrid search (BM25 + vector + RRF)
- [x] Faz 2: Cross-encoder reranking
- [x] Faz 3: Semantic + hierarchical chunking
- [x] Faz 4: RAGAS evaluation + synthetic test set
- [x] Faz 5: Citation verification + hallucination detector
- [x] Faz 6: Langfuse observability
- [x] Faz 7: Self-critique / corrective RAG agent
- [x] Faz 8: Admin analytics dashboard
- [x] Faz 9: Docs + demo + case study

## Demo

5 dakikalık demo senaryosu: [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md)

<!-- Demo screenshots (placeholder'lar) -->
<!-- ![Chat with citations](docs/screenshots/chat.png) -->
<!-- ![Admin analytics](docs/screenshots/admin.png) -->
<!-- ![Langfuse trace](docs/screenshots/langfuse.png) -->
