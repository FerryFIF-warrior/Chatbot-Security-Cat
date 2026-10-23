"""Konfigurasi AI Service Security Cat.

Seluruh parameter RAG diambil dari models/konfigurasi_rag.json agar pipeline
Flask memakai pengaturan yang sama dengan notebook referensi. Nilai rahasia
(GROQ_API_KEY) hanya dibaca dari .env dan tidak pernah dikirim ke client.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency opsional saat smoke test
    def load_dotenv(*_args, **_kwargs):
        return False

load_dotenv(BASE_DIR / ".env")

CONFIG_PATH = BASE_DIR / "models" / "konfigurasi_rag.json"


def _load_rag_config() -> dict:
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        config = json.load(handle)

    folder_db = Path(config.get("folder_db", "data/vectordb"))
    if not folder_db.is_absolute():
        folder_db = BASE_DIR / folder_db
    config["folder_db"] = str(folder_db)

    config.setdefault("nama_koleksi", "materi_security_cat")
    config.setdefault("nama_embedding", "paraphrase-multilingual-MiniLM-L12-v2")
    config.setdefault("jarak", "cosine")
    config.setdefault("k", 3)
    config.setdefault("batas_jarak", 0.7)
    config.setdefault("temperature", 0)
    config.setdefault("max_tokens", 2000)
    config.setdefault("model_llm", "openai/gpt-oss-20b")
    config.setdefault("base_url", "https://api.groq.com/openai/v1")
    config.setdefault("pesan_tidak_ada", "Maaf, informasi tidak ditemukan di dokumen.")
    config.setdefault("system_prompt", "Jawab singkat dalam bahasa Indonesia.")
    config.setdefault(
        "template_prompt",
        "Jawab pertanyaan HANYA berdasarkan konteks berikut. "
        "Jika tidak ada di konteks, tulis: {tidak_ada}\n\n"
        "Konteks:\n{konteks}\n\n"
        "Pertanyaan: {pertanyaan}\nJawaban singkat:",
    )
    return config


RAG_CONFIG = _load_rag_config()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "local").strip().lower()
EMBEDDING_API_URL = os.getenv("EMBEDDING_API_URL", "").strip()
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "").strip()
EMBEDDING_API_MODEL = os.getenv(
    "EMBEDDING_API_MODEL", "text-embedding-3-small"
).strip()
PORT = int(os.getenv("PORT", "8001"))
MAX_QUESTION_LENGTH = int(os.getenv("MAX_QUESTION_LENGTH", "1000"))

DATA_DIR = BASE_DIR / "data"
REGISTRY_PATH = Path(os.getenv("RAG_REGISTRY_PATH", DATA_DIR / "registry.sqlite"))

PESAN_TIDAK_ADA = RAG_CONFIG["pesan_tidak_ada"]
PESAN_UNSAFE = (
    "Maaf, saya hanya dapat membantu pembelajaran keamanan siber yang defensif. "
    "Permintaan untuk menyerang sistem nyata tidak dapat saya bantu."
)
PESAN_ERROR = (
    "AI sedang tidak tersedia - materi & simulator tetap dapat digunakan."
)
