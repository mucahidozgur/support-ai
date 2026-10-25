"""ORM modelleri."""

from app.models.document import Chunk, Document
from app.models.query_log import QueryLog

__all__ = ["Chunk", "Document", "QueryLog"]
