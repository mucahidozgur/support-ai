# Support AI — Mimari Dokümanı

> Enterprise RAG assistant for **SupportHub** — her cevap kaynaklı, hallucination sıfır toleranslı.

## Genel Bakış

Support AI, destek ekiplerinin 5.000+ knowledge base makalesi arasında harcadığı
arama süresini (~%30) saniyelere indiren kurumsal bir RAG asistanıdır. Yanlış cevabın
müşteri kaybettirdiği bir ortamda çalıştığı için sistem, **cevap üretmekten önce
güvenliği garanti eden çok katmanlı bir mimari** üzerine kuruludur:

- Cevap üretilebilmesi için retrieval güven eşiği aşılmalıdır.
- Üretilen her cümle bir kaynağa (document ID + chunk ID + skor) bağlanır.
- Kaynağı olmayan cümleler işaretlenir; yetersiz context'te sistem LLM'i hiç çağırmaz
  ve "Bu bilgi knowledge base'de bulunmuyor." der.
- Kalite sürekli ölçülür (RAGAS) ve her adım izlenir (Langfuse).

## Yüksek Seviye Mimari

```
                        ┌─────────────────────────────┐
                        │        Frontend (Next.js)   │
                        │  /dashboard  /assistant     │
                        │  /admin (KPI + son sorgular)│
                        └──────────────┬──────────────┘
                                       │ HTTP/SSE (3002 → 8002)
                        ┌──────────────▼──────────────┐
                        │        FastAPI (api)        │
                        │  /api/ai/*  /api/analytics  │
                        └──┬────────┬────────┬────────┘
                           │        │        │
              ┌────────────▼──┐  ┌──▼───────────┐  ┌───────────────┐
              │   Services    │  │ LangGraph    │  │ Langfuse      │
              │ RAG/rerank/   │  │ agent        │  │ trace +       │
              │ verification/ │  │ (router: qa, │  │ feedback       │
              │ critique/     │  │  summarize,  │  └───────────────┘
              │ evaluation    │  │  actions,    │
              └──────┬────────┘  │  compare)    │
                     │           └──────┬───────┘
                     │                  │
              ┌──────▼──────────────────▼──────┐       ┌──────────────────┐
              │   PostgreSQL 16 + pgvector    │       │  Groq (qwen)     │
              │  documents / chunks (FTS +    │       │  + yerel modeller│
              │  embeddings) / query_logs     │       │  (bge-small,     │
              └──────────────────────────────┘       │  bge-reranker)   │
                                                     └──────────────────┘
```

## Katmanlar

| Katman | Konum | Sorumluluk |
|---|---|---|
| **Frontend** | `frontend/src/app` | Doküman yönetimi, asistan (SSE), analitik paneli; Zustand auth state |
| **API** | `backend/app/api` | `ai.py` (chat/agent/corrective/evaluate/feedback), `analytics.py`, `documents.py`, `auth.py` |
| **Services** | `backend/app/services` | `rag.py` (hybrid+rerank), `chat.py` (eşik + verification), `critique.py`, `verification.py`, `evaluation.py`, `ingestion.py`, `chunking.py` |
| **Agent** | `backend/app/agent` | LangGraph grafiği: niyet router'ı (qa/summarize/extract/compare) + retrieve node'ları |
| **Core** | `backend/app/core` | Config, DB, LLM/embedding/reranker loader'ları, observability, güvenlik |

## RAG Pipeline

### 1. Ingestion — hiyerarşik chunking
`chunk_text_hierarchical`: Markdown başlıkları (`#`/`##`/`###`) hiyerarşiyi kurar;
her bölüm `RecursiveCharacterTextSplitter` ile 1000/200 sınırında alt chunk'lara
bölünür. **Heading, chunk content'ine prefix olarak işlenir** — chunk tek başına
anlamlı kalır, FTS/embedding başlık kelimelerini görür. `chunks.heading` kolonuna
başlık zinciri ("Ana > Alt") yazılır; `tsv_content` generated kolonu
`to_tsvector('simple', content)` ile otomatik dolar (GIN index'li).

### 2. Retrieval — hybrid search (BM25 + vektör + RRF)
Vektör araması (pgvector cosine, `MIN_SIMILARITY=0.55` filtresi) ve PostgreSQL FTS
(`websearch_to_tsquery` + `ts_rank`) paralel koşar; sonuçlar **Reciprocal Rank
Fusion** ile birleşir: `score = Σ 1/(60 + rank)`, kaynaklar `alpha` ile ağırlıklanır
(0=yalnız BM25, 1=yalnız vektör). Her sonuç `retrieval_source` taşır
("vector"/"bm25"/"both").

### 3. Reranking — cross-encoder
`BAAI/bge-reranker-v2-m3` (lazy singleton, ~2 GB, ilk kullanımda iner) adayların
(query, chunk) çiftlerini skorlar; `similarity` rerank skoruyla güncellenir.
`use_rerank` (varsayılan True) ile kapatılabilir.

### 4. Context expansion — parent retrieval
`expand_context=True` iken rerank'in seçtiği en iyi chunk'ın `heading`'i alınır;
aynı başlıktaki diğer chunk'lar bağlama eklenir (`expanded=True` işaretli).

### 5. Chat + citation verification
Chat akışı: hybrid+rerank → **güven eşiği** (`has_sufficient_context`, 0.55) →
yetersizse LLM **hiç çağrılmaz** (lazy init), sabit "bilgi yok" cevabı stream edilir,
`insufficient_context=true` döner. Yeterliyse LLM stream → her cümle
`verify_citations` ile kaynaklara bağlanır (LLM chunk_id döner; kaynaklarda olmayan
ID'ler NONE sayılır) → `detect_hallucination` 0-1 sadakat skoru üretir (<0.7 =
hallucination). Hepsi SSE `verification` event'inde: `{verified, unsupported,
faithfulness}`.

### 6. Corrective RAG — rewrite + critique
`/api/ai/chat/corrective`: yetersiz context'te `rewrite_query` sorguyu yeniden yazar
ve arama tekrarlanır; taslak cevap `critique_answer` ile eleştirilir, gerekirse
`revised_answer` kullanılır (`max_retries` tur). SSE ek event'leri: `rewrite`,
`critique`, `revision`.

### 7. Observability — Langfuse
Tüm LLM çağrıları `CallbackHandler` ile trace edilir; `search_hybrid`, `rerank`,
`verify_citations` `@observe()` span'leri taşır (query/limit/alpha,
candidates_count/top_k, verified/unsupported_count metadata). `POST /api/ai/feedback`
thumbs up/down'u hem Langfuse'a hem `query_logs`'a yazar. **Anahtarlar boşsa tüm
katman no-op'tur** — observability asla akışı bozmaz.

## Anti-Hallucination Stratejisi (4 Katman)

```
┌─ 1. Retrieval eşiği ─────────────────────────────────────────────┐
│    max(similarity) < 0.55 → LLM çağrılmaz, "bilgi yok" döner     │
├─ 2. Citation verification ───────────────────────────────────────┤
│    Her cümle → chunk_id veya NONE; uydurma ID'ler reddedilir     │
├─ 3. Self-critique ───────────────────────────────────────────────┤
│    Corrective RAG: rewrite → yeniden ara → eleştir → düzelt      │
├─ 4. Sürekli ölçüm ───────────────────────────────────────────────┤
│    RAGAS faithfulness/answer_relevancy/context_precision +       │
│    query_logs analitiği (faithfulness, feedback, latency)        │
└──────────────────────────────────────────────────────────────────┘
```

## Karar Notları

- **Neden hybrid (BM25 + vektör)?** Vektör araması anlam eşleşmesi, FTS birebir
  kelime eşleşmesi yakalar; ikisinin RRF ile birleşimi her ikisinin zayıf yanını
  kapatır (tek başına vektör, nadir teknik terimleri kaçırabilir).
- **Neden cross-encoder rerank?** Bi-encoder embedding skorları geniş aday
  havuzunda gürültülüdür; cross-encoder (query, chunk) çiftini birlikte okuyarak
  çok daha isabetli sıralar. Maliyeti yüksek olduğu için yalnızca ilk 20 adaya
  uygulanır.
- **Neden RAGAS?** "Çalışıyor" demek yetmez — kurumsal müşteri ölçülebilir kalite
  ister. Sentetik test seti + faithfulness/answer_relevancy/context_precision
  hedefleri (F≥0.85, CP≥0.75, AR≥0.80) regresyonları yakalar.
- **Neden PostgreSQL FTS (harici BM25 kütüphanesi yerine)?** `tsv_content`
  generated column + GIN index ile sıfır senkronizasyon kodu; arama ve vektör aynı
  transactional veritabanında kalır.
- **Neden lazy LLM?** Güven eşiği LLM'in inşasından önce koşar; API key'siz
  ortamda bile "bilgi yok" cevabı hatasız döner (Faz 5 canlı testinde yakalanan
  bug'ın çözümü).

## Klasör Yapısı

```
support-ai/
├── backend/
│   ├── app/
│   │   ├── agent/          # LangGraph grafiği + node'lar
│   │   ├── api/            # ai, analytics, documents, auth, deps
│   │   ├── core/           # config, db, llm, observability, security
│   │   ├── models/         # Document, Chunk, QueryLog
│   │   ├── schemas/        # Pydantic v2 modelleri
│   │   └── services/       # rag, chat, critique, verification,
│   │                       # evaluation, ingestion, chunking, prompts
│   ├── alembic/            # migration'lar (4 revizyon)
│   ├── scripts/            # seed_data, run_evaluation (CLI)
│   └── tests/              # 105 test
├── frontend/src/app/dashboard/   # documents, assistant, admin
├── docs/                  # CLIENT_BRIEF, EVALUATION, DEMO_SCRIPT, CASE_STUDY
├── ARCHITECTURE.md        # bu doküman
└── docker-compose.yml     # postgres + api + web (5434/8002/3002)
```
