"""Pipeline RAG Security Cat.

Alur mengikuti notebook referensi:
retrieve(k=3, cosine) -> gate batas_jarak -> augment(template) -> generate(Groq).
Guard unsafe dijalankan sebelum retrieval/LLM. Semua kegagalan Groq dipetakan
menjadi status "error" agar Laravel dan UI tidak menerima exception 500.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from config import (
    EMBEDDING_API_KEY,
    EMBEDDING_API_MODEL,
    EMBEDDING_API_URL,
    EMBEDDING_PROVIDER,
    GROQ_API_KEY,
    PESAN_ERROR,
    PESAN_TIDAK_ADA,
    PESAN_UNSAFE,
    RAG_CONFIG,
    REGISTRY_PATH,
)

logger = logging.getLogger(__name__)

PANJANG_CHUNK = 70
TUMPANG = 15

_UNSAFE_PATTERNS = [
    r"\b(scan|scanning|pindai)\b.{0,30}\b(port|ip|target|server|jaringan|situs|website)\b",
    r"\b(nmap|sqlmap|metasploit|burp suite|hydra|john the ripper|hashcat|nikto|masscan)\b",
    r"\b(buat|buatkan|bikin|bikinkan|tulis|tuliskan|kembangkan|rakit|siapkan)\b.{0,40}\b(malware|virus|ransomware|keylogger|trojan|worm|backdoor|botnet|phishing kit|payload|exploit|reverse shell|spyware)\b",
    r"\b(curi|mencuri|curangi|bobol|membobol|hack|meretas|retas|bypass|lewati)\b.{0,40}\b(akun|password|sandi|login|instagram|facebook|email|sistem|website|situs|server|wifi)\b",
    r"\b(credential|kredensial)\b.{0,30}\b(harvest|harvesting|steal|curi|kumpulkan)\b",
    r"\b(ddos|dos attack|flood)\b.{0,30}\b(target|server|situs|website|ip)\b",
    r"\b(serang|menyerang|attack)\b.{0,30}\b(ip|server|situs|website|target|jaringan)\b",
    r"\b(jual|beli|dapatkan)\b.{0,30}\b(exploit|malware|database bocor|password bocor)\b",
    r"\b(lakukan|praktikkan|jalankan|terapkan)\b.{0,30}\b(sql injection|sqli|xss|csrf|phishing)\b",
    r"\b(buat|buatkan|bikin|bikinkan|tulis|tuliskan)\b.{0,30}\b(script|kode|program)\b.{0,40}\b(mencuri|membobol|menyerang|menyadap)\b",
]

_embedder = None
_collection = None


def _connect_registry() -> sqlite3.Connection:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(REGISTRY_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            judul TEXT NOT NULL,
            sumber TEXT NOT NULL,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'indexed',
            indexed_at TEXT,
            teks TEXT
        )
        """
    )
    connection.commit()
    return connection


def chunk_text(teks: str, panjang: int = PANJANG_CHUNK, tumpang: int = TUMPANG) -> list[str]:
    """Memotong teks menjadi chunk kata dengan overlap, sama seperti notebook."""
    kata = (teks or "").split()
    if not kata:
        return []

    chunks: list[str] = []
    step = max(1, panjang - tumpang)
    for mulai in range(0, len(kata), step):
        chunk = " ".join(kata[mulai:mulai + panjang])
        if chunk:
            chunks.append(chunk)
        if mulai + panjang >= len(kata):
            break
    return chunks


def is_unsafe(question: str) -> bool:
    """Deteksi permintaan serangan nyata tanpa memblokir pertanyaan edukatif."""
    teks = (question or "").lower()
    return any(re.search(pattern, teks) for pattern in _UNSAFE_PATTERNS)


class EmbeddingBackend:
    """Embedding local-first dengan opsi API sesuai EMBEDDING_PROVIDER."""

    def __init__(self) -> None:
        self.provider = EMBEDDING_PROVIDER
        self._local_model = None
        self._api_client = None

    def name(self) -> str:
        if self.provider == "api":
            return f"api:{EMBEDDING_API_MODEL}"
        return f"local:{RAG_CONFIG['nama_embedding']}"

    def __call__(self, input: Iterable[str] | str) -> list[list[float]]:
        texts = [input] if isinstance(input, str) else list(input)
        return self.embed(texts)

    def embed_query(self, input: Iterable[str] | str) -> list[list[float]]:
        return self.__call__(input)

    def embed_documents(self, input: Iterable[str]) -> list[list[float]]:
        return self.embed(list(input))

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self.provider == "api":
            return self._embed_api(texts)
        return self._embed_local(texts)

    def _embed_local(self, texts: list[str]) -> list[list[float]]:
        if self._local_model is None:
            from sentence_transformers import SentenceTransformer

            try:
                self._local_model = SentenceTransformer(
                    RAG_CONFIG["nama_embedding"],
                    local_files_only=True,
                )
            except Exception:
                self._local_model = SentenceTransformer(RAG_CONFIG["nama_embedding"])
        vectors = self._local_model.encode(texts, normalize_embeddings=True)
        return [list(map(float, vector)) for vector in vectors]

    def _embed_api(self, texts: list[str]) -> list[list[float]]:
        if not EMBEDDING_API_KEY or not EMBEDDING_API_URL:
            raise RuntimeError(
                "EMBEDDING_API_KEY dan EMBEDDING_API_URL wajib diisi saat "
                "EMBEDDING_PROVIDER=api."
            )
        if self._api_client is None:
            from openai import OpenAI

            self._api_client = OpenAI(
                api_key=EMBEDDING_API_KEY,
                base_url=EMBEDDING_API_URL,
            )
        response = self._api_client.embeddings.create(
            model=EMBEDDING_API_MODEL,
            input=texts,
        )
        return [list(map(float, item.embedding)) for item in response.data]


def get_embedder() -> EmbeddingBackend:
    global _embedder
    if _embedder is None:
        _embedder = EmbeddingBackend()
    return _embedder


def get_collection():
    global _collection
    if _collection is not None:
        return _collection

    import chromadb

    Path(RAG_CONFIG["folder_db"]).mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=RAG_CONFIG["folder_db"])
    _collection = client.get_or_create_collection(
        name=RAG_CONFIG["nama_koleksi"],
        embedding_function=get_embedder(),
        metadata={"hnsw:space": RAG_CONFIG.get("jarak", "cosine")},
    )
    return _collection


def _index_pages(
    document_id: str,
    judul: str,
    sumber: str,
    pages: list[dict],
) -> int:
    """Upsert halaman/chunk ke ChromaDB dan perbarui registry."""
    collection = get_collection()
    try:
        collection.delete(where={"document_id": document_id})
    except Exception:
        pass

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict] = []

    for page in pages:
        halaman = int(page.get("halaman") or 0)
        for index, chunk in enumerate(chunk_text(page.get("teks", ""))):
            ids.append(f"{document_id}_p{halaman}_c{index}")
            documents.append(chunk)
            metadatas.append(
                {
                    "document_id": document_id,
                    "judul": judul,
                    "sumber": sumber,
                    "halaman": halaman,
                }
            )

    if documents:
        batch_size = 100
        for start in range(0, len(documents), batch_size):
            collection.upsert(
                ids=ids[start:start + batch_size],
                documents=documents[start:start + batch_size],
                metadatas=metadatas[start:start + batch_size],
            )

    status = "indexed" if documents else "empty"
    indexed_at = datetime.now(timezone.utc).isoformat()
    with _connect_registry() as connection:
        connection.execute(
            """
            INSERT INTO documents (id, judul, sumber, chunk_count, status, indexed_at, teks)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                judul = excluded.judul,
                sumber = excluded.sumber,
                chunk_count = excluded.chunk_count,
                status = excluded.status,
                indexed_at = excluded.indexed_at,
                teks = excluded.teks
            """,
            (
                document_id,
                judul,
                sumber,
                len(documents),
                status,
                indexed_at,
                json.dumps(pages, ensure_ascii=False),
            ),
        )
    return len(documents)


def ingest_document(judul: str, sumber: str, teks: str) -> dict:
    document_id = uuid.uuid4().hex
    chunk_count = _index_pages(
        document_id,
        judul.strip(),
        sumber.strip(),
        [{"halaman": 0, "teks": teks}],
    )
    return {"id": document_id, "chunk_count": chunk_count}


def ingest_pdf(path: str | Path, judul: str | None = None) -> dict:
    from pypdf import PdfReader

    pdf_path = Path(path)
    reader = PdfReader(str(pdf_path))
    pages: list[dict] = []
    for number, page in enumerate(reader.pages, start=1):
        text = re.sub(r"\s+", " ", page.extract_text() or "").strip()
        if text:
            pages.append({"halaman": number, "teks": text})

    document_id = uuid.uuid4().hex
    chunk_count = _index_pages(
        document_id,
        judul or pdf_path.stem,
        pdf_path.name,
        pages,
    )
    return {"id": document_id, "chunk_count": chunk_count}


def list_documents() -> list[dict]:
    with _connect_registry() as connection:
        rows = connection.execute(
            "SELECT id, judul, sumber, chunk_count, status, indexed_at "
            "FROM documents ORDER BY indexed_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def delete_document(document_id: str) -> bool:
    try:
        get_collection().delete(where={"document_id": document_id})
    except Exception:
        pass

    with _connect_registry() as connection:
        cursor = connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))
    return cursor.rowcount > 0


def reindex_all() -> dict:
    with _connect_registry() as connection:
        rows = connection.execute("SELECT * FROM documents").fetchall()

    total_chunks = 0
    for row in rows:
        pages = json.loads(row["teks"] or "[]")
        total_chunks += _index_pages(
            row["id"],
            row["judul"],
            row["sumber"],
            pages,
        )
    return {"indexed": len(rows), "total_chunks": total_chunks}


def retrieve(question: str, k: int | None = None):
    collection = get_collection()
    count = collection.count()
    if count == 0:
        raise RuntimeError("Collection ChromaDB masih kosong.")

    limit = min(int(k or RAG_CONFIG["k"]), count)
    result = collection.query(query_texts=[question], n_results=limit)
    return (
        result["ids"][0],
        result["documents"][0],
        result["distances"][0],
        result["metadatas"][0],
    )


def augment(question: str, ids: list[str], texts: list[str]) -> str:
    konteks = "\n".join(f"[{chunk_id}] {teks}" for chunk_id, teks in zip(ids, texts))
    return RAG_CONFIG["template_prompt"].format(
        konteks=konteks,
        pertanyaan=question,
        tidak_ada=PESAN_TIDAK_ADA,
    )


def generate(prompt: str) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY belum diatur pada .env AI Service.")

    from openai import OpenAI

    client = OpenAI(api_key=GROQ_API_KEY, base_url=RAG_CONFIG["base_url"])
    response = client.chat.completions.create(
        model=RAG_CONFIG["model_llm"],
        messages=[
            {"role": "system", "content": RAG_CONFIG["system_prompt"]},
            {"role": "user", "content": prompt},
        ],
        temperature=RAG_CONFIG["temperature"],
        max_tokens=RAG_CONFIG["max_tokens"],
    )
    return (response.choices[0].message.content or "").strip()


def _sources(metadatas: list[dict]) -> list[dict]:
    sources: list[dict] = []
    seen: set[tuple] = set()
    for metadata in metadatas or []:
        document_id = metadata.get("document_id") or ""
        page = int(metadata.get("halaman") or 0)
        key = (document_id, page)
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            {
                "id": document_id,
                "judul": metadata.get("judul") or metadata.get("sumber") or "Materi",
                "halaman": page or None,
            }
        )
    return sources


def answer_question(question: str, history: list[dict] | None = None) -> dict:
    """Jalankan R-A-G dengan gate dua lapis dan fallback status."""
    del history  # Riwayat tidak masuk prompt; konteks wajib berasal dari retrieval.

    question = (question or "").strip()
    result = {
        "answer": "",
        "sources": [],
        "status": "ok",
        "distance": None,
    }

    if not question:
        return {**result, "answer": PESAN_TIDAK_ADA, "status": "not_found"}

    if is_unsafe(question):
        return {**result, "answer": PESAN_UNSAFE, "status": "unsafe"}

    try:
        ids, texts, distances, metadatas = retrieve(question)
    except Exception:
        logger.exception("Retrieval gagal")
        return {**result, "answer": PESAN_ERROR, "status": "error"}

    if not distances:
        return {**result, "answer": PESAN_TIDAK_ADA, "status": "not_found"}

    distance = float(distances[0])
    result["distance"] = distance
    if distance > float(RAG_CONFIG["batas_jarak"]):
        return {**result, "answer": PESAN_TIDAK_ADA, "status": "not_found"}

    prompt = augment(question, ids, texts)
    try:
        answer = generate(prompt)
    except Exception:
        logger.exception("Groq gagal menghasilkan jawaban")
        return {**result, "answer": PESAN_ERROR, "status": "error"}

    if not answer:
        return {**result, "answer": PESAN_ERROR, "status": "error"}

    return {
        "answer": answer,
        "sources": _sources(metadatas),
        "status": "ok",
        "distance": distance,
    }


def health() -> dict:
    try:
        chunks = get_collection().count()
        status = "ok"
    except Exception:
        logger.exception("Health check ChromaDB gagal")
        chunks = 0
        status = "error"

    return {
        "status": status,
        "kb_chunks": chunks,
        "model_llm": RAG_CONFIG["model_llm"],
        "embedding": RAG_CONFIG["nama_embedding"] if EMBEDDING_PROVIDER == "local"
        else EMBEDDING_API_MODEL,
    }
