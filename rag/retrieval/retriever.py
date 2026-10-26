"""Hybrid retrieval: 0.7 * tf-idf cosine + 0.3 * keyword overlap."""

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from sklearn.metrics.pairwise import cosine_similarity

from rag.ingestion.ingest import INDEX_PATH, fit_vectorizer, run_ingestion
from rag.safety import sanitize_text

load_dotenv()

MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.12"))

STOP_WORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "for",
    "of",
    "to",
    "in",
    "on",
    "is",
    "are",
    "what",
    "which",
    "why",
    "how",
    "this",
    "that",
    "with",
    "show",
    "me",
    "should",
    "be",
    "it",
    "do",
    "does",
    "alarm",
    "alarms",
    "procedure",
    "applies",
    "over",
    "last",
    "days",
    "recommend",
}


def keywords(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9\-]+", text.lower())
    return {w for w in words if w not in STOP_WORDS and len(w) > 2}


class DocumentRetriever:
    def __init__(self, index_path: Path = INDEX_PATH, min_score: float = MIN_SCORE):
        index_path = Path(index_path)
        if not index_path.exists():
            # First run: build the index automatically
            run_ingestion(index_path=index_path)

        with open(index_path, encoding="utf-8") as file:
            index = json.load(file)

        self.chunks = index["chunks"]
        self.documents = index["documents"]
        self.built_at = index["built_at"]
        self.min_score = min_score
        self.vectorizer, self.matrix = fit_vectorizer(self.chunks)

    def search(
        self,
        query: str,
        top_k: int = 4,
        doc_types: list[str] | None = None,
        equipment_types: list[str] | None = None,
        max_per_doc: int = 3,
    ) -> dict:
        """
        Returns:
        {
          "query": ..., "filters": ...,
          "status": "ok" | "low_confidence" | "no_results",
          "results": [ {chunk fields..., "score": 0.43, "citation": "[SOP-BFP-001 section ...]"} ]
        }
        """
        filters = {"doc_types": doc_types, "equipment_types": equipment_types}

        # 1) metadata filtering
        allowed = []
        for i, chunk in enumerate(self.chunks):
            if doc_types and chunk["doc_type"] not in doc_types:
                continue
            if equipment_types and not (set(chunk["equipment_types"]) & set(equipment_types)):
                continue
            allowed.append(i)

        if not allowed or not query.strip():
            return {"query": query, "filters": filters, "status": "no_results", "results": []}

        # 2) scoring
        query_vector = self.vectorizer.transform([query])
        cosine = cosine_similarity(query_vector, self.matrix[allowed]).ravel()
        query_words = keywords(query)

        scored = []
        for position, i in enumerate(allowed):
            chunk = self.chunks[i]
            chunk_words = keywords(f"{chunk['title']} {chunk['section']} {chunk['text']}")
            overlap = len(query_words & chunk_words) / len(query_words) if query_words else 0.0
            score = 0.7 * float(cosine[position]) + 0.3 * overlap
            scored.append((score, i))

        scored.sort(reverse=True)

        # keep at most `max_per_doc` chunks from one document, so other documents can be cited too
        picked = []
        per_doc = {}
        for score, i in scored:
            doc_id = self.chunks[i]["doc_id"]
            if score <= 0 or per_doc.get(doc_id, 0) >= max_per_doc:
                continue
            per_doc[doc_id] = per_doc.get(doc_id, 0) + 1
            picked.append((score, i))
            if len(picked) == top_k:
                break

        results = []
        for score, i in picked:
            chunk = dict(self.chunks[i])
            # 3) prompt-injection protection: remove suspicious sentences
            clean_text, flagged = sanitize_text(chunk["text"])
            chunk["text"] = clean_text
            chunk["injection_removed"] = flagged
            chunk["score"] = round(score, 3)
            chunk["citation"] = format_citation(chunk)
            results.append(chunk)

        if not results:
            status = "no_results"
        elif results[0]["score"] < self.min_score:
            status = "low_confidence"
        else:
            status = "ok"

        # Drop weak extra hits so they do not get cited
        if status == "ok":
            results = [r for r in results if r["score"] >= self.min_score * 0.75]

        return {"query": query, "filters": filters, "status": status, "results": results}


def format_citation(chunk: dict) -> str:
    """SOP-BFP-001 - Boiler Feed Pump Operating Procedure, section "..." """
    return f'{chunk["doc_id"]} - {chunk["title"]}, section "{chunk["section"]}"'
