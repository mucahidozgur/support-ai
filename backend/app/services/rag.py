"""RAG arama servisi (pgvector cosine similarity + PostgreSQL FTS + RRF)."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import get_embeddings, get_reranker
from app.models.document import Chunk, Document

# Bu eşiğin altındaki benzerlikler ilgisiz kabul edilir. Faz 3a'da gerçek modelle
# ölçülerek belirlendi: ilgili sorgu 0.68-0.82, ilgisiz sorgu 0.40-0.47 üretti.
MIN_SIMILARITY = 0.55

# RRF formülündeki yumuşatma sabiti: score = sum(1 / (k + rank)).
RRF_K = 60


def rrf_fuse(
    vector_results: list[dict],
    bm25_results: list[dict],
    k: int = RRF_K,
    vector_weight: float = 1.0,
    bm25_weight: float = 1.0,
) -> list[dict]:
    """İki sıralı listeyi Reciprocal Rank Fusion ile birleştirir.

    Her kaynağın katkısı 1 / (k + rank) (rank 1'den başlar); aynı chunk
    her iki listede varsa katkılar toplanır. Sonuçlar toplam skora göre
    büyükten küçüğe sıralanır; beraberlikte chunk_id'ye göre deterministik.

    Çıktıdaki her elemana retrieval_source ("vector", "bm25" veya "both")
    eklenir; similarity alanı birleşik RRF skoru olur.
    """
    fused: dict[object, dict] = {}

    for rank, item in enumerate(vector_results):
        entry = fused.setdefault(
            item["chunk_id"],
            {**item, "retrieval_source": "vector", "rrf_score": 0.0},
        )
        entry["rrf_score"] += vector_weight / (k + rank + 1)

    for rank, item in enumerate(bm25_results):
        entry = fused.setdefault(
            item["chunk_id"],
            {**item, "retrieval_source": "bm25", "rrf_score": 0.0},
        )
        if entry["retrieval_source"] == "vector":
            entry["retrieval_source"] = "both"
        entry["rrf_score"] += bm25_weight / (k + rank + 1)

    results = [{**entry, "similarity": entry.pop("rrf_score")} for entry in fused.values()]
    return sorted(results, key=lambda r: (r["similarity"], str(r["chunk_id"])), reverse=True)


class RAGService:
    """Query embedding'i ile pgvector üzerinde benzerlik araması."""

    def __init__(self, db: AsyncSession, owner_id: UUID) -> None:
        self.db = db
        self.owner_id = owner_id
        self.embeddings = get_embeddings()

    async def search(
        self,
        query: str,
        document_ids: list[UUID] | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """En benzer chunk'ları döndürür; owner filtresi JOIN ile uygulanır."""
        query_emb = self.embeddings.embed_query(query)
        similarity = (1 - Chunk.embedding.cosine_distance(query_emb)).label("similarity")
        stmt = (
            select(Chunk, Document.title, similarity)
            .join(Document, Document.id == Chunk.document_id)
            .where(Document.owner_id == self.owner_id)
            .where(similarity >= MIN_SIMILARITY)
            .order_by(similarity.desc())
            .limit(limit)
        )
        if document_ids is not None:
            stmt = stmt.where(Chunk.document_id.in_(document_ids))

        rows = (await self.db.execute(stmt)).all()
        return [
            {
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "document_title": title,
                "content": chunk.content,
                "similarity": float(sim),
                "chunk_index": chunk.chunk_index,
                "heading": chunk.heading,
            }
            for chunk, title, sim in rows
        ]

    async def search_bm25(self, query: str, limit: int = 20) -> list[dict]:
        """PostgreSQL FTS ile kelime tabanlı arama (websearch_to_tsquery + ts_rank).

        tsv_content generated column'u 'simple' config ile üretilir; aynı config
        sorguda da kullanıldığı için token'lar birebir eşleşir. Owner filtresi
        JOIN ile uygulanır. similarity alanı ts_rank skoru taşır (0-sınırlı
        değildir; yalnızca sıralama anlamı taşır).
        """
        if not query.strip():
            return []
        tsquery = func.websearch_to_tsquery("simple", query)
        rank = func.ts_rank(Chunk.tsv_content, tsquery).label("rank")
        stmt = (
            select(Chunk, Document.title, rank)
            .join(Document, Document.id == Chunk.document_id)
            .where(Document.owner_id == self.owner_id)
            .where(Chunk.tsv_content.op("@@")(tsquery))
            .order_by(rank.desc())
            .limit(limit)
        )
        rows = (await self.db.execute(stmt)).all()
        return [
            {
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "document_title": title,
                "content": chunk.content,
                "similarity": float(rank_val),
                "chunk_index": chunk.chunk_index,
                "heading": chunk.heading,
            }
            for chunk, title, rank_val in rows
        ]

    async def search_hybrid(self, query: str, limit: int = 5, alpha: float = 0.5) -> list[dict]:
        """Vektör + BM25 sonuçlarını RRF ile birleştirir.

        alpha: 0.0 → yalnız BM25, 1.0 → yalnız vektör, 0.5 → eşit ağırlık.
        Her kaynaktan limit * 2 aday toplanır; birleşik listeden ilk limit döner.
        """
        pool = limit * 2
        vector_results = await self.search(query, limit=pool) if alpha > 0.0 else []
        bm25_results = await self.search_bm25(query, limit=pool) if alpha < 1.0 else []
        fused = rrf_fuse(
            vector_results,
            bm25_results,
            vector_weight=alpha,
            bm25_weight=1.0 - alpha,
        )
        return fused[:limit]

    async def rerank(self, query: str, candidates: list[dict], top_k: int = 3) -> list[dict]:
        """Cross-encoder ile adayları (query, content) çiftlerine bakarak yeniden sıralar.

        Her adayda "content" alanı zorunludur (yoksa ValueError). Çıktı rerank
        skoruna göre azalan sıralıdır; her elemana "rerank_score" eklenir ve
        "similarity" alanı rerank skoruyla güncellenir (sıralama ile tutarlı
        kalsın diye). İlk top_k eleman döner. Boş liste hatasız [] döner.
        """
        if not candidates:
            return []
        if any("content" not in c for c in candidates):
            raise ValueError("rerank adaylarında 'content' alanı zorunlu")

        reranker = get_reranker()
        pairs = [(query, c["content"]) for c in candidates]
        scores = [float(s) for s in reranker.predict(pairs)]

        ranked = [
            {**candidate, "similarity": score, "rerank_score": score}
            for candidate, score in zip(candidates, scores, strict=True)
        ]
        ranked.sort(key=lambda r: (r["rerank_score"], str(r["chunk_id"])), reverse=True)
        return ranked[:top_k]

    async def search_hybrid_rerank(
        self,
        query: str,
        limit: int = 3,
        alpha: float = 0.5,
        rerank_candidates: int = 20,
        expand_context: bool = False,
    ) -> list[dict]:
        """Hybrid arama → cross-encoder rerank: en iyi limit chunk'ı döndürür.

        Akış: search_hybrid(limit=rerank_candidates) aday havuzunu kurar,
        rerank(top_k=limit) bunlardan en isabetli olanları seçer.

        expand_context=True ise (parent retrieval): en iyi chunk'ın heading'i
        alınır ve aynı başlıktaki diğer chunk'lar sonuca eklenir (rerank'te
        zaten olanlar çıkarılır; eklenenler expanded=True işaretlenir).
        """
        candidates = await self.search_hybrid(query, limit=rerank_candidates, alpha=alpha)
        results = await self.rerank(query, candidates, top_k=limit)
        if expand_context and results:
            top_heading = results[0].get("heading")
            extra = await self.get_chunks_by_heading(top_heading, limit=5)
            seen = {r["chunk_id"] for r in results}
            results = [
                *results,
                *[{**chunk, "expanded": True} for chunk in extra if chunk["chunk_id"] not in seen],
            ]
        return results

    async def get_all_chunks(self, document_id: UUID) -> list[dict]:
        """Belirtilen dokümanın TÜM chunk'larını döner (chunk_index sıralı).

        Owner filtresi uygulanır. similarity alanı 1.0 ile doldurulur —
        burada semantik skor yok, chunk'lar dokümanın kendisi.
        """
        stmt = (
            select(Chunk, Document.title)
            .join(Document, Document.id == Chunk.document_id)
            .where(Document.owner_id == self.owner_id)
            .where(Document.id == document_id)
            .order_by(Chunk.chunk_index)
        )
        rows = (await self.db.execute(stmt)).all()
        return [
            {
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "document_title": title,
                "content": chunk.content,
                "similarity": 1.0,
                "chunk_index": chunk.chunk_index,
                "heading": chunk.heading,
            }
            for chunk, title in rows
        ]

    async def get_chunks_by_heading(self, heading: str | None, limit: int = 5) -> list[dict]:
        """Aynı başlığa (parent) ait chunk'ları chunk_index sırasıyla döndürür.

        Parent retrieval: rerank'in seçtiği en iyi chunk'ın bölümündeki diğer
        chunk'ları bağlama eklemek için kullanılır. Boş heading için [] döner.
        """
        if not heading:
            return []
        stmt = (
            select(Chunk, Document.title)
            .join(Document, Document.id == Chunk.document_id)
            .where(Document.owner_id == self.owner_id)
            .where(Chunk.heading == heading)
            .order_by(Chunk.chunk_index)
            .limit(limit)
        )
        rows = (await self.db.execute(stmt)).all()
        return [
            {
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "document_title": title,
                "content": chunk.content,
                "similarity": 0.0,  # skorlanmadı; yalnızca bağlam genişletmesi
                "chunk_index": chunk.chunk_index,
                "heading": chunk.heading,
            }
            for chunk, title in rows
        ]
