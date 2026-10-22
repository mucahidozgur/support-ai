# Support AI

Enterprise RAG assistant for customer support teams.

Built for **SupportHub** (B2B SaaS) — every answer cites its source,
zero tolerance for hallucination.

## The problem we solve

SupportHub's agents spend 30% of their time searching 5,000+ KB articles.
Wrong answers cost enterprise customers. Support AI retrieves the right
answer in seconds — **with proof** (source document + chunk + similarity).

## Features

- 💬 RAG chat with citations
- 📋 Ticket summarization
- ✍️ Suggested response generation
- 📊 Evaluation dashboard (RAGAS)
- 🔍 Full observability (Langfuse)

## Stack

**Backend:** FastAPI, SQLAlchemy 2.0 async, LangGraph, LangChain
**AI:** Groq (qwen-3.8-27b), sentence-transformers (bge-small-en-v1.5), BM25, bge-reranker
**DB:** PostgreSQL 16 + pgvector
**Frontend:** Next.js 14 App Router, TypeScript, Tailwind
**Infra:** Docker Compose

## Quick start

```bash
# 1. Setup
cp .env.example .env
# Edit .env — add GROQ_API_KEY

# 2. Build & run
docker compose build api
docker compose up -d postgres api

# 3. Health check
curl http://127.0.0.1:8002/health
# {"status":"ok","service":"support-ai"}

# 4. Frontend (dev)
cd frontend && npm install && npm run dev
# → http://localhost:3002