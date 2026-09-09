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
        fingerprint = sorted([
            {
                "source": document["source"],
                "mtime": document["mtime"],
                "size": len(document["text"]),
            }
            for document in documents
        ], key=lambda item: item["source"])
        if not documents:
            self.store.build([])
            self.store.source_fingerprint = []
            if self.store.index_path.exists():
                self.store.save()
            return 0

        if (
            not rebuild
            and self.store.load()
            and self.store.source_fingerprint == fingerprint
        ):
            return len(self.store.chunks)

        chunks = split_documents(documents)
        self.store.build(chunks)
        self.store.source_fingerprint = fingerprint
        self.store.save()
        return len(chunks)

    def search(self, query: str, top_k: int = None) -> List[Dict]:
        if not self.store.chunks:
            self.ensure_index()
        return self.store.search(query, top_k or self.top_k)

    def build_context(self, query: str, top_k: int = None, max_chars: int = 3500) -> str:
        results = self.search(query, top_k)
        return self.format_context(results, max_chars=max_chars)

    def format_context(self, results: List[Dict], max_chars: int = 3500) -> str:
        """Format evidence with stable IDs that can be retained in the report."""
        if not results:
            return ""

        parts = []
        used = 0
        for index, item in enumerate(results, 1):
            evidence_id = f"S{index}"
            snippet = (
                f"[{evidence_id}] 来源: {item['source']}, "
                f"片段: {item['chunk_id']}, 相关度: {item['score']}\n{item['text']}"
            )
            if used + len(snippet) > max_chars:
                continue
            item["evidence_id"] = evidence_id
            parts.append(snippet)
            used += len(snippet)
        return "\n\n".join(parts)
