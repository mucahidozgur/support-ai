"""LLM prompt template'leri: değişiklikleri tek yerden yapmak için."""

from typing import Any

SYSTEM_PROMPT = """Sen Support AI'ın AI asistanısın. Kullanıcının dokümanları
hakkında soruları yanıtlarsın.

KURALLAR:
- SADECE sana verilen BAĞLAM (context) içindeki bilgileri kullan.
- Bağlamda cevap yoksa açıkça "Bu bilgi dokümanlarınızda bulunmuyor" de.
- Uydurma. Kaynağı olmayan hiçbir iddiada bulunma.
- Türkçe soruya Türkçe, İngilizce soruya İngilizce cevap ver.
- Kısa ve net ol. Gerektiğinde madde işaretleri kullan.
- Cevabın sonunda hangi dokümandan yararlandığını belirtme —
  kaynaklar ayrıca frontend'e gönderiliyor.
"""

SUMMARIZE_SYSTEM = """Sen Support AI'ın özet çıkarma asistanısın. Verilen
dokümanı kısa ve öz bir şekilde özetlersin.

KURALLAR:
- SADECE verilen metni kullan, dışarıdan bilgi ekleme.
- 3-5 cümlelik özet + gerekirse madde işaretli ana noktalar.
- Türkçe metne Türkçe, İngilizce metne İngilizce cevap.
- Kısa ve net ol."""

EXTRACT_ACTIONS_SYSTEM = """Sen Support AI'ın aksiyon çıkarma asistanısın.
Verilen dokümandan yapılması gereken işleri (aksiyon maddeleri) çıkarırsın.

KURALLAR:
- SADECE verilen metni kullan.
- Her aksiyonu "- [ ] " ile başlat (checkbox formatı).
- Sorumlu/tarih varsa belirt.
- Eğer dokümanda aksiyon yoksa açıkça "Bu dokümanda belirgin bir aksiyon
  maddesi yok" de.
- Kısa ve net ol."""

COMPARE_SYSTEM = """Sen Support AI'ın doküman karşılaştırma asistanısın.
İki dokümanı yan yana koyup benzerlikleri ve farkları çıkarırsın.

KURALLAR:
- SADECE verilen iki metni kullan.
- Markdown tablo ile karşılaştır: | Kriter | Doküman A | Doküman B |.
- Ardından "## Ortak Noktalar" ve "## Farklar" bölümleri.
- Kısa ve net ol."""


def build_context_block(chunks: list[dict[str, Any]]) -> str:
    """Chunk listesini LLM'e verilecek context bloğuna çevirir.

    Her chunk için:
      [Kaynak {i+1}] {document_title} (parça {chunk_index})
      {content}
      ---
    """
    blocks = [
        f"[Kaynak {i + 1}] {chunk['document_title']} (parça {chunk['chunk_index']})\n"
        f"{chunk['content']}\n---"
        for i, chunk in enumerate(chunks)
    ]
    return "\n".join(blocks)


def build_user_prompt(query: str, context_block: str) -> str:
    """User mesajını BAĞLAM bloğu ve sorguyla oluşturur."""
    return f"BAĞLAM:\n{context_block}\n\nSORU: {query}"


def _join_contents(chunks: list[dict[str, Any]]) -> str:
    """Chunk içeriklerini paragraf ayraçlarıyla birleştirir."""
    return "\n\n".join(chunk["content"] for chunk in chunks)


def build_summarize_user_prompt(chunks: list[dict[str, Any]]) -> str:
    """Summarize user promptu: dokümanın tüm chunk içeriğini gömer."""
    return f"Aşağıdaki dokümanı özetle:\n\n{_join_contents(chunks)}"


def build_extract_actions_user_prompt(chunks: list[dict[str, Any]]) -> str:
    """Extract_actions user promptu: dokümanın tüm chunk içeriğini gömer."""
    return f"Aşağıdaki dokümandan aksiyon maddelerini çıkar:\n\n{_join_contents(chunks)}"


def build_compare_user_prompt(
    chunks_a: list[dict[str, Any]], chunks_b: list[dict[str, Any]]
) -> str:
    """Compare user promptu: iki dokümanı etiketli bloklar halinde gömer."""
    title_a = chunks_a[0]["document_title"] if chunks_a else "?"
    title_b = chunks_b[0]["document_title"] if chunks_b else "?"
    return (
        f"DOKÜMAN A ({title_a}):\n{_join_contents(chunks_a)}\n\n---\n\n"
        f"DOKÜMAN B ({title_b}):\n{_join_contents(chunks_b)}"
    )
