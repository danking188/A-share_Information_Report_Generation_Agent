import re
from typing import Dict, List


def split_text(text: str, chunk_size: int = 900, overlap: int = 120) -> List[str]:
    """Split text into overlapping chunks."""
    clean_text = re.sub(r"\s+", " ", text).strip()
    if not clean_text:
        return []

    chunks = []
    start = 0
    while start < len(clean_text):
        end = min(start + chunk_size, len(clean_text))
        chunks.append(clean_text[start:end])
        if end >= len(clean_text):
            break
        start = max(end - overlap, start + 1)

    return chunks


def split_documents(documents: List[Dict], chunk_size: int = 900, overlap: int = 120) -> List[Dict]:
    """Split loaded documents into indexed chunks."""
    chunks = []
    for document in documents:
        for idx, chunk_text in enumerate(split_text(document["text"], chunk_size, overlap)):
            chunks.append({
                "id": f"{document['source']}#{idx + 1}",
                "source": document["source"],
                "text": chunk_text,
            })
    return chunks
