"""Metin chunking yardımcıları."""

import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

# Satır başındaki Markdown başlıkları (h1-h3).
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$")


def _make_splitter(max_chunk_size: int, overlap: int) -> RecursiveCharacterTextSplitter:
    """Ortak konfigürasyonlu metin bölücü üretir."""
    return RecursiveCharacterTextSplitter(
        chunk_size=max_chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
    )


def chunk_text(text: str, chunk_size: int = 800, chunk_overlap: int = 100) -> list[str]:
    """Metni anlamlı parçalara böler; boş parçaları filtreler."""
    splitter = _make_splitter(chunk_size, chunk_overlap)
    return [chunk for chunk in splitter.split_text(text) if chunk.strip()]


def chunk_text_hierarchical(
    text: str, max_chunk_size: int = 1000, overlap: int = 200
) -> list[dict]:
    """Metni Markdown başlık hiyerarşisine göre parçalar.

    1. Metin `#`/`##`/`###` başlıklarına göre bölünür; her bölüm, başlık
       zincirini ("Ana > Alt > ...") heading olarak taşır.
    2. Başlık yoksa metin paragraflara (`\\n\\n`) göre bölünür (heading None).
    3. Her bölüm RecursiveCharacterTextSplitter ile max_chunk_size/overlap
       sınırına göre alt chunk'lara ayrılır; heading, bölümün TÜM chunk'larına
       content prefix'i olarak işlenir (chunk tek başına anlamlı kalsın ve
       FTS/embedding başlık kelimelerini görsün diye).

    Dönüş: [{"content", "heading", "chunk_index"}, ...]; chunk_index global sayaçtır.
    """
    splitter = _make_splitter(max_chunk_size, overlap)
    sections: list[tuple[str | None, str]] = []  # (heading, body)
    headings: list[str] = []
    body_lines: list[str] = []
    has_headings = False

    def flush() -> None:
        body = "\n".join(body_lines).strip()
        if body:
            heading = " > ".join(headings) if headings else None
            sections.append((heading, body))

    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            has_headings = True
            flush()
            body_lines = []
            del headings[len(match.group(1)) - 1 :]  # hiyerarşiyi seviyeye göre kırp
            headings.append(match.group(2).strip())
        else:
            body_lines.append(line)
    flush()

    if not has_headings:
        # Başlık yok: paragraf sınırlarını bölüm sınırı say.
        sections = [(None, p.strip()) for p in text.split("\n\n") if p.strip()]

    chunks: list[dict] = []
    chunk_index = 0
    for heading, body in sections:
        section_text = f"{heading}\n{body}" if heading else body
        for piece in splitter.split_text(section_text):
            piece = piece.strip()
            if not piece:
                continue
            chunks.append({"content": piece, "heading": heading, "chunk_index": chunk_index})
            chunk_index += 1
    return chunks
