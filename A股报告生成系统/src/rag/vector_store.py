import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List


def tokenize(text: str) -> List[str]:
    """Tokenize mixed Chinese and alphanumeric text for lightweight retrieval."""
    tokens = []
    lowered = text.lower()
    tokens.extend(re.findall(r"[a-z0-9_]{2,}", lowered))
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
    tokens.extend(chinese_chars)
    tokens.extend(
        "".join(pair)
        for pair in zip(chinese_chars, chinese_chars[1:])
    )
    return tokens


class LocalVectorStore:
    """Small local TF-IDF style store for text chunks."""

    def __init__(self, index_dir: str):
        self.index_dir = Path(index_dir)
        self.index_path = self.index_dir / "index.json"
        self.chunks: List[Dict] = []
        self.idf: Dict[str, float] = {}

    def build(self, chunks: List[Dict]) -> None:
        self.chunks = []
        doc_freq = Counter()
        chunk_terms = []

        for chunk in chunks:
            terms = Counter(tokenize(chunk["text"]))
            chunk_terms.append(terms)
            doc_freq.update(terms.keys())

        total = max(len(chunks), 1)
        self.idf = {
            term: math.log((1 + total) / (1 + freq)) + 1
            for term, freq in doc_freq.items()
        }

        for chunk, terms in zip(chunks, chunk_terms):
            norm = self._norm(terms)
            self.chunks.append({
                **chunk,
                "terms": dict(terms),
                "norm": norm,
            })

    def save(self) -> None:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "chunks": self.chunks,
            "idf": self.idf,
        }
        self.index_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def load(self) -> bool:
        if not self.index_path.exists():
            return False
        payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        self.chunks = payload.get("chunks", [])
        self.idf = payload.get("idf", {})
        return True

    def search(self, query: str, top_k: int = 6) -> List[Dict]:
        query_terms = Counter(tokenize(query))
        query_norm = self._norm(query_terms)
        if not query_terms or query_norm == 0:
            return []

        scored = []
        for chunk in self.chunks:
            score = self._cosine(query_terms, query_norm, Counter(chunk.get("terms", {})), chunk.get("norm", 0))
            if score > 0:
                scored.append({
                    "score": round(score, 4),
                    "source": chunk["source"],
                    "text": chunk["text"],
                })

        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:top_k]

    def _weight(self, term: str, count: int) -> float:
        return count * self.idf.get(term, 1.0)

    def _norm(self, terms: Counter) -> float:
        return math.sqrt(sum(self._weight(term, count) ** 2 for term, count in terms.items()))

    def _cosine(self, query_terms: Counter, query_norm: float, chunk_terms: Counter, chunk_norm: float) -> float:
        if chunk_norm == 0:
            return 0.0
        common = set(query_terms).intersection(chunk_terms)
        dot = sum(
            self._weight(term, query_terms[term]) * self._weight(term, chunk_terms[term])
            for term in common
        )
        return dot / (query_norm * chunk_norm)
