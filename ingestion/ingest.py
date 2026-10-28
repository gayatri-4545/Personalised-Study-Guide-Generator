"""
Ingestion pipeline for the Personalized Study Guide Generator.

Pipeline:
    knowledge_base/<Subject>/<Document>.pdf
        -> load pages
        -> chunk (RecursiveCharacterTextSplitter)
        -> embed (sentence-transformers, local — swap for OpenAI if preferred)
        -> upsert into Qdrant with retrieval metadata

Metadata written per chunk (see spec section 5 — Qdrant):
    chunk_id, document_id, page_number, subject, chapter, source_file

Run:
    pip install -r requirements.txt
    python ingest.py
"""

import sys
import uuid
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pdfplumber
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

from config.settings import settings

# ---- Config (pulled from .env via config/settings.py) --------------------
KNOWLEDGE_BASE_DIR = settings.KNOWLEDGE_BASE_DIR
QDRANT_URL = settings.QDRANT_URL
QDRANT_COLLECTION = settings.QDRANT_COLLECTION
EMBEDDING_MODEL = settings.LOCAL_EMBEDDING_MODEL  # local embedder — see settings.EMBEDDING_PROVIDER
CHUNK_SIZE = settings.CHUNK_SIZE
CHUNK_OVERLAP = settings.CHUNK_OVERLAP
# -------------------------------------------------------------------------


def document_id_from_path(pdf_path: Path) -> str:
    """Stable, human-readable document_id, e.g. DEEP_LEARNING_CNN."""
    subject = pdf_path.parent.name.upper()
    name = pdf_path.stem.upper().replace(" ", "_")
    return f"{subject}_{name}"


def chunk_id_from(document_id: str, page: int, chunk_index: int) -> str:
    raw = f"{document_id}_p{page}_c{chunk_index}"
    # Qdrant point IDs must be uint or UUID — derive a stable UUID from the raw string
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, raw))


def extract_toc_from_bookmarks(pdf_path: Path) -> list[dict]:
    """Read the PDF's embedded outline/bookmarks, if present. Most textbooks have this."""
    toc = []
    try:
        reader = PdfReader(str(pdf_path))

        def walk(outlines, level=0):
            for item in outlines:
                if isinstance(item, list):
                    walk(item, level + 1)
                else:
                    try:
                        page_num = reader.get_destination_page_number(item) + 1
                    except Exception:
                        continue
                    title = getattr(item, "title", str(item)).strip()
                    if title:
                        toc.append({"title": title, "page": page_num, "level": level})

        walk(reader.outline)
    except Exception:
        pass
    return sorted(toc, key=lambda e: e["page"])


def extract_toc_from_fontsize(pdf_path: Path, size_ratio_threshold: float = 1.15) -> list[dict]:
    """
    Fallback heading detection for textbooks with no embedded bookmarks.
    Flags lines whose average font size is notably larger than the document's
    most common (body-text) font size.
    """
    toc = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            sizes = []
            for page in pdf.pages[:30]:
                sizes.extend(round(ch["size"], 1) for ch in page.chars)
            if not sizes:
                return toc
            body_size = max(set(sizes), key=sizes.count)
            threshold = body_size * size_ratio_threshold

            for page_num, page in enumerate(pdf.pages, start=1):
                lines: dict[int, list] = {}
                for ch in page.chars:
                    lines.setdefault(round(ch["top"]), []).append(ch)
                for top, chars in sorted(lines.items()):
                    text = "".join(c["text"] for c in chars).strip()
                    if not text or len(text) > 120 or text[0].islower():
                        continue
                    avg_size = sum(c["size"] for c in chars) / len(chars)
                    if avg_size >= threshold:
                        toc.append({"title": text, "page": page_num, "level": 1})
    except Exception:
        pass
    return toc


def build_toc(pdf_path: Path) -> list[dict]:
    toc = extract_toc_from_bookmarks(pdf_path)
    if toc:
        return toc
    return extract_toc_from_fontsize(pdf_path)


def heading_for_page(page_number: int, toc: list[dict]) -> tuple[str | None, str | None]:
    """
    Returns (chapter, subtopic) for a given page: the most recent level-0
    heading is the chapter; the most recent heading at any level is the subtopic.
    """
    chapter = None
    subtopic = None
    for entry in toc:
        if entry["page"] > page_number:
            break
        subtopic = entry["title"]
        if entry["level"] == 0:
            chapter = entry["title"]
    return chapter, subtopic


def load_and_chunk(pdf_path: Path) -> list[dict]:
    """Load a full textbook PDF, detect chapter/subtopic structure, chunk with overlap, attach metadata."""
    loader = PyPDFLoader(str(pdf_path))
    pages = loader.load()  # one Document per page, page.metadata['page'] = 0-indexed

    toc = build_toc(pdf_path)
    source = "bookmarks" if toc and any(e["level"] == 0 for e in toc) else ("fontsize" if toc else "none")
    print(f"  TOC source: {source} ({len(toc)} headings detected)")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    doc_id = document_id_from_path(pdf_path)
    subject = pdf_path.parent.name

    records = []
    for page in pages:
        page_number = page.metadata.get("page", 0) + 1  # display as 1-indexed
        chapter, subtopic = heading_for_page(page_number, toc)
        chunks = splitter.split_text(page.page_content)
        for i, chunk_text in enumerate(chunks):
            if not chunk_text.strip():
                continue
            records.append(
                {
                    "id": chunk_id_from(doc_id, page_number, i),
                    "text": chunk_text.strip(),
                    "document_id": doc_id,
                    "chunk_id": f"{doc_id}_CH_{page_number}_{i}",
                    "page_number": page_number,
                    "subject": subject,
                    "chapter": chapter,
                    "subtopic": subtopic,
                    "source_file": pdf_path.name,
                }
            )
    return records


def ensure_collection(client: QdrantClient, dim: int):
    existing = [c.name for c in client.get_collections().collections]
    if QDRANT_COLLECTION not in existing:
        client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        print(f"Created Qdrant collection '{QDRANT_COLLECTION}' (dim={dim})")


def main():
    pdf_paths = sorted(KNOWLEDGE_BASE_DIR.rglob("*.pdf"))
    if not pdf_paths:
        print(f"No PDFs found under {KNOWLEDGE_BASE_DIR}. Add files first — see project spec section 6.")
        return

    print(f"Found {len(pdf_paths)} PDF(s). Loading model '{EMBEDDING_MODEL}'...")
    model = SentenceTransformer(EMBEDDING_MODEL)
    dim = model.get_sentence_embedding_dimension()

    client = QdrantClient(url=QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)
    ensure_collection(client, dim)

    all_records = []
    for pdf_path in pdf_paths:
        print(f"Chunking {pdf_path.relative_to(KNOWLEDGE_BASE_DIR)} ...")
        records = load_and_chunk(pdf_path)
        all_records.extend(records)

        subtopics = sorted({r["subtopic"] for r in records if r["subtopic"]})
        if subtopics:
            preview = ", ".join(subtopics[:8])
            more = f" (+{len(subtopics) - 8} more)" if len(subtopics) > 8 else ""
            print(f"  Detected subtopics: {preview}{more}")
        else:
            print("  No subtopics detected — chunks will have chapter/subtopic = None. "
                  "Consider hand-labeling or checking if the PDF has a real TOC.")

    print(f"Total chunks: {len(all_records)}. Embedding + upserting...")

    batch_size = 64
    for i in tqdm(range(0, len(all_records), batch_size)):
        batch = all_records[i : i + batch_size]
        texts = [r["text"] for r in batch]
        vectors = model.encode(texts, show_progress_bar=False).tolist()

        points = [
            PointStruct(
                id=rec["id"],
                vector=vec,
                payload={
                    "text": rec["text"],
                    "document_id": rec["document_id"],
                    "chunk_id": rec["chunk_id"],
                    "page_number": rec["page_number"],
                    "subject": rec["subject"],
                    "chapter": rec["chapter"],
                    "subtopic": rec["subtopic"],
                    "source_file": rec["source_file"],
                },
            )
            for rec, vec in zip(batch, vectors)
        ]
        client.upsert(collection_name=QDRANT_COLLECTION, points=points)

    print(f"Done. Ingested {len(all_records)} chunks into '{QDRANT_COLLECTION}'.")


if __name__ == "__main__":
    main()
