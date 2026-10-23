"""HTTP API AI Service Security Cat.

Endpoint internal ini dipanggil Laravel (bukan browser). Tidak ada CORS dan
tidak ada API key yang dikembalikan pada respons mana pun.
"""

from __future__ import annotations

import logging

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

import rag
from config import MAX_QUESTION_LENGTH, PORT

logging.basicConfig(level=logging.INFO)
for noisy_logger in ("sentence_transformers", "httpx2", "huggingface_hub"):
    logging.getLogger(noisy_logger).setLevel(logging.WARNING)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024


@app.get("/")
def index():
    """Daftar endpoint agar pemanggilan manual tidak menebak-nebak URL."""
    return jsonify(
        {
            "service": "AI Service Security Cat",
            "endpoints": {
                "GET /health": "Status service & jumlah dokumen",
                "POST /chat": '{"question": "...", "history": []}',
                "GET /documents": "Daftar dokumen",
                "POST /documents": '{"judul": "...", "sumber": "...", "teks": "..."}',
                "DELETE /documents/<id>": "Hapus dokumen",
                "POST /reindex": "Bangun ulang index vektor",
            },
        }
    )


@app.get("/health")
def health():
    return jsonify(rag.health())


@app.post("/chat")
def chat():
    payload = request.get_json(silent=True) or {}
    question = payload.get("question")

    if not isinstance(question, str) or not question.strip():
        return jsonify(
            {
                "answer": "Pertanyaan tidak boleh kosong.",
                "sources": [],
                "status": "error",
                "distance": None,
            }
        ), 422

    if len(question) > MAX_QUESTION_LENGTH:
        return jsonify(
            {
                "answer": f"Pertanyaan maksimal {MAX_QUESTION_LENGTH} karakter.",
                "sources": [],
                "status": "error",
                "distance": None,
            }
        ), 422

    history = payload.get("history") if isinstance(payload.get("history"), list) else []
    return jsonify(rag.answer_question(question, history))


@app.get("/documents")
def documents():
    return jsonify({"documents": rag.list_documents()})


@app.post("/documents")
def create_document():
    payload = request.get_json(silent=True) or {}
    judul = str(payload.get("judul") or "").strip()
    sumber = str(payload.get("sumber") or "").strip()
    teks = str(payload.get("teks") or "").strip()

    if not judul or not sumber or not teks:
        return jsonify({"error": "judul, sumber, dan teks wajib diisi."}), 422
    if len(teks) < 20:
        return jsonify({"error": "teks terlalu pendek untuk di-index."}), 422

    result = rag.ingest_document(judul=judul, sumber=sumber, teks=teks)
    return jsonify(result), 201


@app.delete("/documents/<document_id>")
def delete_document(document_id: str):
    deleted = rag.delete_document(document_id)
    return jsonify({"deleted": deleted})


@app.post("/reindex")
def reindex():
    return jsonify(rag.reindex_all())


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    if isinstance(error, HTTPException):
        return jsonify({"error": error.description}), error.code

    logging.exception("AI Service error", exc_info=error)
    if request.path == "/chat":
        return jsonify(
            {
                "answer": "AI sedang tidak tersedia - materi & simulator tetap dapat digunakan.",
                "sources": [],
                "status": "error",
                "distance": None,
            }
        )
    return jsonify({"error": "AI service internal error."}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, debug=False)
