from pathlib import Path
from typing import Dict, List


SUPPORTED_EXTENSIONS = {".md", ".txt"}


def load_documents(raw_dir: str) -> List[Dict]:
    """Load plain text knowledge documents from a directory."""
    base = Path(raw_dir)
    if not base.exists():
        return []

    documents = []
    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        try:
            text = path.read_text(encoding="utf-8").strip()
        except UnicodeDecodeError:
            text = path.read_text(encoding="gb18030", errors="ignore").strip()

        if text:
            documents.append({
                "source": str(path.relative_to(base)),
                "text": text,
                "mtime": path.stat().st_mtime,
            })

    return documents
