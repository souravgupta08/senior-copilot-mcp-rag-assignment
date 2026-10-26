# RAG Design

## Source document types

| doc_type | Documents | Equipment |
|---|---|---|
| `operating_procedure` | SOP-BFP-001 Boiler Feed Pump Operating Procedure, SOP-MTR-004 Motor Trip Response, SOP-BLR-007 Boiler Drum Level & Alarm Flood | pump, motor, boiler/drum |
| `maintenance_manual` | MM-PMP-002 Centrifugal Pump Maintenance Manual, MM-EXC-008 Discharge Cooler Maintenance, VB-009 Vendor Bulletin (external, contains an injection attempt) | pump, heat exchanger, compressor |
| `troubleshooting_guide` | TG-CMP-003 Gas Compressor Troubleshooting, TG-VLV-006 Control Valve Troubleshooting | compressor, valve |
| `safety_instruction` | SAF-005 Alarm Response Safety Instructions | general |

All documents are synthetic (written for this assignment) and stored as Markdown in `rag/documents/`.

## Ingestion flow

```text
rag/documents/*.md
   -> load_documents()        read file, parse front matter, add source_file + checksum
   -> chunk_document()        split by "## " section; long sections split by paragraph (max 900 chars, 150 overlap)
   -> looks_like_injection()  flag suspicious chunks
   -> build_index()           chunks + document metadata
   -> save_index()            rag/index/alarm_docs_index.json
```

Command: `python -m rag.ingestion.ingest` (also run automatically in the Docker build and on first use of the retriever).
Latest report: [`test-evidence/rag-ingestion-report.json`](test-evidence/rag-ingestion-report.json) – 9 documents, 35 chunks, 1 flagged chunk (`VB-009#c01`).

## Text extraction

Markdown and `.txt` files are read as UTF-8 text. The front matter block (`--- key: value ---`) becomes metadata and is removed from the text.
PDF/DOCX are not in the sample corpus; adding them only needs a new loader in `load_documents()` (e.g. `pypdf`), the rest of the pipeline is unchanged.

## Chunking strategy

- **Section-based**: one chunk per `##` section, because procedures are written section by section ("High Discharge Pressure Alarm Response", "Restart Rules"). A section is a natural unit for a citation.
- Sections longer than 900 characters are split by paragraph; a single very long paragraph is cut with 150 characters of overlap so a sentence is not lost between chunks.

## Chunk metadata

```json
{
  "chunk_id": "SOP-BFP-001#c01",
  "doc_id": "SOP-BFP-001",
  "title": "Boiler Feed Pump Operating Procedure",
  "doc_type": "operating_procedure",
  "equipment_types": ["pump"],
  "applies_to": "Boiler Feed Pump 101, Boiler Feed Pump 102",
  "version": "3.2",
  "trust_level": "internal",
  "source_file": "SOP-BFP-001_boiler_feed_pump_operating_procedure.md",
  "section": "High Discharge Pressure Alarm Response",
  "chunk_index": 1,
  "char_count": 847,
  "contains_injection": false
}
```

## Embedding model / retrieval method

**TF-IDF with unigrams + bigrams** (`sklearn.TfidfVectorizer`, English stop words, sub-linear TF) – an "equivalent retrieval approach" allowed by the brief.

Why: the corpus is small and full of exact technical terms (`FCV-101`, `discharge pressure`, `lube oil`) where lexical matching works very well; it needs no API key, no GPU, no downloads, is deterministic (tests are stable) and explainable. The retriever class is the only place that would change to use neural embeddings.

## Vector database / index

The index is a **JSON file** (`rag/index/alarm_docs_index.json`) with chunks and metadata. The TF-IDF matrix is rebuilt in memory from these chunks when the retriever starts (milliseconds for this corpus). JSON instead of pickle means nothing executable is loaded from disk.

## Hybrid search and ranking

```text
score = 0.7 * cosine(TF-IDF(query), TF-IDF(chunk)) + 0.3 * keyword_overlap(query, chunk)
```

`keyword_overlap` = share of the query's important words that appear in the chunk (title + section + text). Results are sorted by score, and at most 3 chunks per document are kept (`max_per_doc`) so that several documents can be cited. No separate re-ranker – the indexed text repeats the section heading so headings weigh more.

## Retrieval filters

- `equipment_types` – set by the workflow from the resolved asset type + related asset types + `general` (e.g. a pump investigation searches pump, valve, motor, vessel and general documents).
- `doc_types` – available for callers (tested), e.g. only `operating_procedure`.
- If the filtered search is weak, the workflow searches again without filters and says so in the warnings.

## Citation construction

Each returned chunk gets `citation = '<doc_id> - <title>, section "<section>"'`. In the answer, chunks are numbered `D1..Dn`; tool results are referenced as `T<step>`. The GUI shows for each citation: doc id, title, section, score, doc type, file, chunk id and the full chunk text.

Example citations (from a real run):

- `[D1] SOP-BFP-001 - Boiler Feed Pump Operating Procedure, section "Recurring High Discharge Pressure"`
- `[D2] SOP-BFP-001 - Boiler Feed Pump Operating Procedure, section "High Discharge Pressure Alarm Response"`
- `[D5] MM-PMP-002 - Centrifugal Pump Maintenance Manual, section "Likely Causes of High Discharge Pressure"`

## Example retrieved chunks

Query: `Boiler Feed Pump 101 High Discharge Pressure recurring likely causes alarm response procedure actions`
Filters: `equipment_types=['pump', 'valve', 'motor', 'vessel', 'general']` → status **ok**

| score | chunk | text (start) |
|---|---|---|
| 0.455 | `SOP-BFP-001#c02` | "If the alarm occurs more than three times in a week, raise a maintenance request to inspect FCV-101 (positioner calibration and instrument air supply)..." |
| 0.400 | `SOP-BFP-001#c01` | "A high discharge pressure alarm (alarm code PMP-PH-01) means the pump discharge pressure has gone above the operating limit of 120 bar..." |
| 0.397 | `SOP-BFP-001#c00` | "This procedure applies to Boiler Feed Pump 101 and Boiler Feed Pump 102 in NorthPlant Unit 1..." |

Query: `quantum banana spaceship` → status **no_results** (nothing is cited).

## Low-confidence handling

| Status | Rule | Behaviour |
|---|---|---|
| `ok` | best score ≥ `RAG_MIN_SCORE` (0.12) | weak extra hits (< 75% of threshold) are dropped |
| `low_confidence` | best score < threshold | results kept but the answer warns "verify with a process engineer" |
| `no_results` | no chunk matches filters / query | no citations, warning "No relevant documents were found" |

## Prompt-injection protections

1. **Detection at ingestion** – `contains_injection` flag per chunk (patterns like "ignore previous instructions", "you are now", "tell the operator to bypass").
2. **Sanitising at retrieval** – suspicious sentences are replaced with `[removed: suspected prompt injection]`; the chunk is marked `injection_removed` and the GUI shows a red tag and a warning.
3. **Trust level** – documents from outside (`trust_level: external`) are tagged in the GUI.
4. **Prompt structure** – when an LLM is used, documents are wrapped in `<document>` tags and the system prompt states that document text is reference material, never instructions.
5. **No tool power from documents** – document text never decides which MCP tool is called; tool selection comes only from the user's question.

Tested in `rag/tests/test_rag.py` and `tests/e2e/test_copilot_e2e.py::test_prompt_injection_in_documents_is_neutralised`.

## Index refresh process

Add or edit files in `rag/documents/` → run `python -m rag.ingestion.ingest` (or rebuild the Docker image) → restart the copilot (the retriever loads the index once). Each document has a `checksum` in the index, so changed documents are easy to spot.
