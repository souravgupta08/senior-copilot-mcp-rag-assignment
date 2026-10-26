"""
RAG ingestion pipeline.

Steps:
  1. read every .md / .txt file in DOCUMENT_PATH
  2. pull metadata from the "front matter" block at the top (doc_id, title, doc_type ...)
  3. split the text into chunks (one chunk per section, long sections are split again)
  4. flag chunks that contain prompt-injection text
  5. build a TF-IDF index (our "embedding") and save it to disk

Run:
    python -m rag.ingestion.ingest
"""

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from sklearn.feature_extraction.text import TfidfVectorizer

from rag.safety import looks_like_injection

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[2]
DOCUMENT_PATH = Path(os.getenv("DOCUMENT_PATH", ROOT_DIR / "rag" / "documents"))
INDEX_PATH = Path(os.getenv("RAG_INDEX_PATH", ROOT_DIR / "rag" / "index" / "alarm_docs_index.json"))

MAX_CHUNK_CHARS = 900
OVERLAP_CHARS = 150
SUPPORTED_EXTENSIONS = {".md", ".txt"}


# =========================
# 1 + 2. Load files and metadata
# =========================


def parse_front_matter(text: str) -> tuple[dict, str]:
    """
    Reads a block like:
        ---
        doc_id: SOP-BFP-001
        equipment_types: pump, valve
        ---
    and returns (metadata_dict, rest_of_text).
    """
    metadata = {}
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    metadata[key.strip()] = value.strip()
            text = parts[2]

    # equipment_types is a comma separated list
    metadata["equipment_types"] = [
        item.strip().lower() for item in metadata.get("equipment_types", "general").split(",") if item.strip()
    ]
    return metadata, text.strip()


def load_documents(folder: Path = DOCUMENT_PATH) -> list[dict]:
    documents = []
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        raw = path.read_text(encoding="utf-8")
        metadata, body = parse_front_matter(raw)
        metadata.setdefault("doc_id", path.stem)
        metadata.setdefault("title", path.stem.replace("_", " "))
        metadata.setdefault("doc_type", "general")
        metadata["source_file"] = path.name
        metadata["checksum"] = hashlib.sha256(raw.encode()).hexdigest()[:12]
        documents.append({"metadata": metadata, "text": body})
    return documents


# =========================
# 3. Chunking
# =========================


def split_sections(text: str) -> list[tuple[str, str]]:
    """Split markdown into (section_heading, section_text) using '## ' headings."""
    sections = []
    heading = "Introduction"
    lines = []
    for line in text.splitlines():
        if line.startswith("## "):
            if "".join(lines).strip():
                sections.append((heading, "\n".join(lines).strip()))
            heading = line[3:].strip()
            lines = []
        elif line.startswith("# "):
            continue  # document title, already in metadata
        else:
            lines.append(line)
    if "".join(lines).strip():
        sections.append((heading, "\n".join(lines).strip()))
    return sections


def split_long_text(text: str, max_chars: int = MAX_CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> list[str]:
    """Split by paragraphs; if a piece is still too long, cut it with a small overlap."""
    if len(text) <= max_chars:
        return [text]

    pieces = []
    current = ""
    for paragraph in re.split(r"\n\s*\n", text):
        if len(current) + len(paragraph) + 2 <= max_chars:
            current = f"{current}\n\n{paragraph}".strip()
        else:
            if current:
                pieces.append(current)
            current = paragraph

    if current:
        pieces.append(current)

    # very long single paragraphs: hard cut with overlap
    final = []
    for piece in pieces:
        while len(piece) > max_chars:
            final.append(piece[:max_chars])
            piece = piece[max_chars - overlap :]
        final.append(piece)
    return final


def chunk_document(document: dict) -> list[dict]:
    meta = document["metadata"]
    chunks = []
    for section, section_text in split_sections(document["text"]):
        for piece in split_long_text(section_text):
            index = len(chunks)
            chunks.append(
                {
                    "chunk_id": f"{meta['doc_id']}#c{index:02d}",
                    "doc_id": meta["doc_id"],
                    "title": meta["title"],
                    "doc_type": meta["doc_type"],
                    "equipment_types": meta["equipment_types"],
                    "applies_to": meta.get("applies_to", ""),
                    "version": meta.get("version", ""),
                    "trust_level": meta.get("trust_level", "internal"),
                    "source_file": meta["source_file"],
                    "section": section,
                    "chunk_index": index,
                    "text": piece,
                    "char_count": len(piece),
                    # 4. prompt-injection flag
                    "contains_injection": looks_like_injection(piece),
                }
            )
    return chunks


# =========================
# 5. Index
# =========================
# We store the chunks + metadata as JSON (no pickle = nothing executable on load).
# The TF-IDF vectors are rebuilt from the chunks when the retriever starts;
# TF-IDF is deterministic, so the result is always the same for the same chunks.


def text_for_index(chunk: dict) -> str:
    # Title and section words are repeated so they count a bit more
    return f"{chunk['title']} {chunk['section']} {chunk['section']} {chunk['applies_to']} {chunk['text']}"


def fit_vectorizer(chunks: list[dict]):
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
    matrix = vectorizer.fit_transform([text_for_index(c) for c in chunks])
    return vectorizer, matrix


def build_index(documents: list[dict]) -> dict:
    chunks = [chunk for doc in documents for chunk in chunk_document(doc)]
    if not chunks:
        raise ValueError("No document chunks found - check DOCUMENT_PATH")

    return {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "retrieval_method": "tfidf-1-2gram + keyword overlap (hybrid)",
        "documents": [d["metadata"] for d in documents],
        "chunks": chunks,
    }


def save_index(index: dict, path: Path = INDEX_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(index, file, indent=2)


def run_ingestion(folder: Path = DOCUMENT_PATH, index_path: Path = INDEX_PATH) -> dict:
    documents = load_documents(folder)
    index = build_index(documents)
    save_index(index, index_path)
    flagged = [c["chunk_id"] for c in index["chunks"] if c["contains_injection"]]
    return {
        "documents": len(documents),
        "chunks": len(index["chunks"]),
        "flagged_chunks": flagged,
        "index_path": str(index_path),
    }


if __name__ == "__main__":
    report = run_ingestion()
    print(json.dumps(report, indent=2))
