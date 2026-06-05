from pathlib import Path
from typing import Dict, List

from .document_loader import load_documents
from .text_splitter import split_documents
from .vector_store import LocalVectorStore


class RAGRetriever:
    """Retrieve local knowledge snippets for report generation."""

    def __init__(self, knowledge_base_dir: str, top_k: int = 6):
        self.knowledge_base_dir = Path(knowledge_base_dir)
        self.raw_dir = self.knowledge_base_dir / "raw"
        self.index_dir = self.knowledge_base_dir / "index"
        self.top_k = top_k
        self.store = LocalVectorStore(str(self.index_dir))

    def ensure_index(self, rebuild: bool = False) -> int:
        documents = load_documents(str(self.raw_dir))
        if not documents:
            self.store.build([])
            return 0

        newest_source_mtime = max(document["mtime"] for document in documents)
        index_is_current = (
            self.store.index_path.exists()
            and self.store.index_path.stat().st_mtime >= newest_source_mtime
        )

        if not rebuild and index_is_current and self.store.load():
            return len(self.store.chunks)

        chunks = split_documents(documents)
        self.store.build(chunks)
        self.store.save()
        return len(chunks)

    def search(self, query: str, top_k: int = None) -> List[Dict]:
        if not self.store.chunks:
            self.ensure_index()
        return self.store.search(query, top_k or self.top_k)

    def build_context(self, query: str, top_k: int = None, max_chars: int = 3500) -> str:
        results = self.search(query, top_k)
        if not results:
            return ""

        parts = []
        used = 0
        for item in results:
            snippet = f"[来源: {item['source']}, 相关度: {item['score']}]\n{item['text']}"
            if used + len(snippet) > max_chars:
                break
            parts.append(snippet)
            used += len(snippet)
        return "\n\n".join(parts)
