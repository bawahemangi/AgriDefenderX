"""
Retrieval half of the advisory RAG pipeline.

Uses TF-IDF (scikit-learn) rather than neural embeddings deliberately:
it needs no model download (this environment has no access to download
sentence-transformer weights from huggingface.co) and for a small,
curated knowledge base of a few dozen documents, TF-IDF keyword matching
on disease/crop names is actually a very strong, easily-debuggable
retriever. If you later grow the knowledge base to hundreds of documents
covering nuanced phrasing, swap this for a sentence-transformer +
vector store (e.g. ChromaDB) using the same retrieve() interface.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

KB_DIR = Path(__file__).parent / "knowledge_base"


@dataclass
class RetrievedDoc:
    filename: str
    title: str
    content: str
    score: float


class AdvisoryRetriever:
    def __init__(self, kb_dir: Path = KB_DIR):
        self.kb_dir = kb_dir
        self.docs: list[tuple[str, str, str]] = []  # (filename, title, content)
        self._load_docs()
        self.vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        self._matrix = self.vectorizer.fit_transform([d[2] for d in self.docs])

    def _load_docs(self):
        for path in sorted(self.kb_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            title = text.splitlines()[0].lstrip("# ").strip() if text else path.stem
            self.docs.append((path.name, title, text))

    def retrieve(self, query: str, top_k: int = 2, min_score: float = 0.05) -> list[RetrievedDoc]:
        query_vec = self.vectorizer.transform([query])
        sims = cosine_similarity(query_vec, self._matrix)[0]
        order = sims.argsort()[::-1][:top_k]
        results = []
        for i in order:
            if sims[i] < min_score:
                continue
            filename, title, content = self.docs[i]
            results.append(RetrievedDoc(filename, title, content, float(sims[i])))
        return results


_retriever_cache = None


def get_retriever() -> AdvisoryRetriever:
    global _retriever_cache
    if _retriever_cache is None:
        _retriever_cache = AdvisoryRetriever()
    return _retriever_cache


def build_query(crop: str, disease: str, growth_stage: str = "") -> str:
    return f"{crop} {disease} {growth_stage} disease pest management".strip()


if __name__ == "__main__":
    r = get_retriever()
    for query in [
        build_query("Tomato", "Early blight", "flowering"),
        build_query("Potato", "Late blight"),
        build_query("Maize", "Fall armyworm"),
        build_query("Tomato", "healthy"),
    ]:
        hits = r.retrieve(query)
        print(f"\nQuery: {query!r}")
        for h in hits:
            print(f"  -> {h.title}  (score={h.score:.3f}, file={h.filename})")
