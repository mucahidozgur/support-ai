# Case Study: Support AI — Zero-Hallucination Enterprise RAG for SupportHub

## The Problem

SupportHub, a B2B SaaS customer-support platform, serves enterprise customers who
do not tolerate wrong answers. Its 5,000+ knowledge-base articles grew faster than
its support agents could navigate them: agents spent roughly 30% of their time
searching for the right article, and every incorrect answer risked losing a
customer. SupportHub needed an assistant that retrieves the right answer in seconds
— and, critically, that **never invents one**. The brief was explicit: every answer
must cite its source (document ID + chunk ID + similarity score), and when retrieval
confidence is too low, the system must say "this is not in the knowledge base"
rather than guess.

## The Solution

I built Support AI, an enterprise RAG system with a **four-layer anti-hallucination
defense**:

1. **Retrieval threshold** — if the best retrieved chunk scores below 0.55, the LLM
   is not called at all; the system answers "not found."
2. **Citation verification** — every sentence of every answer is checked against its
   sources by an LLM judge; sentences without a supporting chunk are flagged, and
   chunk IDs the model invents are rejected.
3. **Self-critique** — a corrective mode rewrites the query when context is
   insufficient, re-searches, critiques the draft answer, and revises it when needed.
4. **Continuous measurement** — RAGAS metrics (faithfulness ≥ 0.85, context
   precision ≥ 0.75, answer relevancy ≥ 0.80) run against synthetically generated
   test sets, and Langfuse traces every step.

## What I Built

**Retrieval pipeline.** Documents are chunked hierarchically: Markdown headings
define sections, each section is split recursively, and every chunk carries its
heading so it stays meaningful on its own. Search is hybrid — pgvector cosine
similarity fused with PostgreSQL full-text search (BM25-style ranking) via
Reciprocal Rank Fusion, with an alpha weight between the two. A cross-encoder
(bge-reranker-v2-m3) re-ranks the top 20 candidates before the best 3-5 chunks go
to the LLM, and parent retrieval expands context by pulling sibling chunks from the
same heading.

**Backend.** FastAPI with async SQLAlchemy 2.0 and Alembic migrations, a LangGraph
agent that routes queries across four intents (QA, summarize, extract actions,
compare), SSE streaming with a verification event, a RAGAS evaluation service with
synthetic test-set generation, and an analytics layer that logs every query with
its faithfulness score, latency, and user feedback.

**Frontend.** A Next.js 14 dashboard for document management, an assistant chat
with citations, and an admin analytics page with KPI cards, a recent-queries table,
and top-query rankings.

**Observability.** Langfuse callbacks on every LLM call, manual spans on retrieval
and reranking with input metadata, and a feedback endpoint — all designed to be a
no-op when keys are absent, so observability can never break the product.

## Technical Challenges

**Hybrid fusion that actually works.** Vector search captures meaning but misses
exact technical terms; keyword search finds them but ignores semantics. RRF fusion
of both, tuned with an alpha parameter, outperformed either alone — and the fusion
function keeps a deterministic tie-break so evaluation runs are reproducible.

**Reranking on a budget.** The cross-encoder is dramatically more accurate than the
bi-encoder but 20× slower and needs ~2 GB of RAM. It is loaded lazily as a singleton
and applied only to the 20 candidates the hybrid stage already narrowed down — full
accuracy, no cold-start cost, and the image never carries the model.

**A live-caught production bug.** The first version constructed the chat LLM at
service init; with an empty API key, even the "not found" path crashed. Making the
LLM lazy — constructed only after the confidence threshold passes — means the system
answers honestly with no key at all. The live test that caught this became a
regression test.

## Results

Nine phases, 105 passing tests, a fully containerized stack (Postgres 16 + pgvector,
FastAPI, Next.js), migrations for every schema change, and zero invented answers:
below the confidence threshold the system refuses to answer, by design.

## How I'd Apply This to Your Project

The same playbook transfers directly: hybrid retrieval over your vector store,
cross-encoder reranking for precision, a hard confidence gate before generation,
per-sentence citation checks, and RAGAS + tracing from day one — so accuracy is
measured, not assumed.
