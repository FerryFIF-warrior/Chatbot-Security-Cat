"""Ingest materi PDF dari folder `seed` ke ChromaDB.

Struktur folder seed: satu subfolder per topik, tiap subfolder berisi PDF
bernama `<Topik>-01.pdf`, `<Topik>-02.pdf`, dan seterusnya, contoh:

    seed/Materi Pishhing/MateriPhishing-01.pdf
    seed/Materi SQL Injection/MateriSQLInjection-01.pdf
    seed/Materi Brute Force/MateriBruteForce-01.pdf
    seed/Materi Authentication Attack/MateriAuthenticationAttack-01.pdf

Judul dokumen disusun dari nama topik (folder) + nomor bagian, sehingga chip
sumber pada jawaban menunjuk materi yang tepat.

Jalankan setelah `pip install -r requirements.txt`:
    python seed_documents.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from config import CONFIG_PATH
from rag import ingest_pdf, list_documents

SEED_DIR = Path(__file__).resolve().parent / "seed"

TOPIC_TITLES = {
    "pishhing": "Phishing Website Detection",
    "phishing": "Phishing Website Detection",
    "authentication": "Multi-Factor Authentication (MFA)",
    "sql injection": "SQL Injection dan Mitigasinya",
    "sql-injection": "SQL Injection dan Mitigasinya",
    "brute force": "Brute Force dan Rate Limiting",
    "brute-force": "Brute Force dan Rate Limiting",
}

LEGACY_TITLES = {
    "phishing": "Phishing Website Detection",
    "mfa": "Multi-Factor Authentication (MFA)",
    "sql-injection": "SQL Injection dan Mitigasinya",
    "brute-force": "Brute Force dan Rate Limiting",
}


def _topic_title(pdf: Path) -> str | None:
    """Ambil judul topik dari nama folder induk (case-insensitive)."""
    folder = re.sub(r"\s+", " ", pdf.parent.name.strip().lower())
    for keyword, title in TOPIC_TITLES.items():
        if keyword in folder:
            return title
    return None


def _judul(pdf: Path) -> str:
    """Susun judul dokumen: topik + nomor bagian (bila ada)."""
    tema = _topic_title(pdf) or LEGACY_TITLES.get(pdf.stem.lower())
    bagian = re.search(r"(\d+)$", pdf.stem)
    if tema and bagian:
        return f"{tema} - Bagian {int(bagian.group(1)):02d}"
    if tema:
        return tema
    return pdf.stem


def _seed_pdfs() -> list[Path]:
    """Kumpulkan semua PDF di dalam `seed` secara rekursif, urut per topik."""
    if not SEED_DIR.exists():
        return []
    pdfs = (path for path in SEED_DIR.rglob("*.pdf") if path.is_file())
    return sorted(
        pdfs,
        key=lambda path: (path.parent.name.lower(), path.name.lower()),
    )


def main() -> int:
    existing = {row["sumber"] for row in list_documents()}
    pdfs = _seed_pdfs()

    if not pdfs:
        print(f"Tidak ada PDF di {SEED_DIR}.")
        return 1

    inserted = 0
    for pdf in pdfs:
        if pdf.name in existing:
            print(f"Lewati (sudah ada): {pdf.relative_to(SEED_DIR)}")
            continue
        judul = _judul(pdf)
        result = ingest_pdf(pdf, judul=judul)
        inserted += 1
        print(
            f"Ingested {pdf.relative_to(SEED_DIR)} [{judul}]: "
            f"{result['chunk_count']} chunk"
        )

    documents = list_documents()
    stored_config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    stored_config.update(
        {
            "jumlah_dokumen": len(documents),
            "total_chunk": sum(int(row["chunk_count"]) for row in documents),
            "sumber_pdf": sorted(row["sumber"] for row in documents),
            "chunk_per_sumber": {
                row["sumber"]: int(row["chunk_count"]) for row in documents
            },
        }
    )
    CONFIG_PATH.write_text(
        json.dumps(stored_config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Selesai. {inserted} dokumen baru, total {len(documents)} dokumen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
