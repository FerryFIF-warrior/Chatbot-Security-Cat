# AI Service Security Cat — Panduan Menjalankan

Backend **Flask** untuk chatbot RAG (Retrieval-Augmented Generation) Security Cat.
Service ini menyediakan API JSON internal yang dipanggil oleh aplikasi Laravel —
**bukan halaman web untuk browser**, tidak ada CORS, dan `GROQ_API_KEY` tidak pernah
dikirim ke client.

- **Port default:** `8001` (ubah lewat variabel `PORT` di `.env`)
- **LLM:** `openai/gpt-oss-20b` via Groq (`https://api.groq.com/openai/v1`)
- **Embedding:** `paraphrase-multilingual-MiniLM-L12-v2` (lokal, default) atau via API
- **Vector DB:** ChromaDB di `data/vectordb` + registry SQLite di `data/registry.sqlite`

---

## 1. Prasyarat

| Kebutuhan | Keterangan |
|---|---|
| Python 3.10+ | Dikembangkan & diuji dengan Python 3.10 |
| `pip` | Untuk menginstal dependency |
| Internet | Saat pertama: unduh model embedding dari HuggingFace; setelah itu model dipakai lokal. Juga dibutuhkan untuk memanggil Groq saat `/chat` |
| Disk ~1 GB | Model embedding lokal + dependency (`chromadb`, `sentence-transformers`) |

---

## 2. Instalasi

Semua perintah dijalankan dari **root proyek** (folder tempat file `app.py` berada).

```bash
# 1. Buat virtualenv (sekali saja)
python -m venv .venv

# 2. Aktifkan virtualenv
source .venv/Scripts/activate      # Windows (Git Bash)
# .venv\Scripts\activate           # Windows (PowerShell/CMD)
# source .venv/bin/activate        # Linux / macOS

# 3. Instal dependency (sekali saja)
pip install -r requirements.txt
```

Isi `requirements.txt`:

```
flask>=3.0,<4
openai>=1.0,<3
chromadb>=0.5,<2
sentence-transformers>=3.0,<6
pypdf>=4.0,<7
python-dotenv>=1.0,<2
```

---

## 3. Konfigurasi `.env`

Salin template lalu isi API key Groq milik Anda:

```bash
cp .env.example .env
```

Dapatkan API key gratis di <https://console.groq.com/keys>, lalu edit `.env`:

```ini
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxx   # wajib untuk endpoint /chat
EMBEDDING_PROVIDER=local            # local | api
PORT=8001
MAX_QUESTION_LENGTH=1000

# Opsional — hanya bila EMBEDDING_PROVIDER=api
EMBEDDING_API_URL=
EMBEDDING_API_KEY=
EMBEDDING_API_MODEL=text-embedding-3-small
```

| Variabel | Wajib | Default | Fungsi |
|---|---|---|---|
| `GROQ_API_KEY` | ✅ (untuk `/chat`) | — | API key Groq; hanya dibaca server, tidak pernah dikirim ke client |
| `EMBEDDING_PROVIDER` | ❌ | `local` | `local` = model embedding lokal; `api` = pakai API embedding external |
| `EMBEDDING_API_URL` | ❌ | — | Endpoint API embedding (saat provider `api`) |
| `EMBEDDING_API_KEY` | ❌ | — | API key embedding (saat provider `api`) |
| `EMBEDDING_API_MODEL` | ❌ | `text-embedding-3-small` | Nama model embedding API |
| `PORT` | ❌ | `8001` | Port HTTP server |
| `MAX_QUESTION_LENGTH` | ❌ | `1000` | Batas karakter pertanyaan `/chat` |
| `RAG_REGISTRY_PATH` | ❌ | `data/registry.sqlite` | Lokasi database registry dokumen |

> ⚠️ **`.env` jangan pernah di-commit atau dikirim ke browser.** File ini sudah ada
> di `.gitignore`.

### Konfigurasi RAG (`models/konfigurasi_rag.json`)

Parameter pipeline RAG diambil dari file ini agar Flask memakai pengaturan yang sama
dengan notebook referensi:

| Kunci | Nilai | Fungsi |
|---|---|---|
| `folder_db` | `data/vectordb` | Lokasi penyimpanan ChromaDB |
| `nama_koleksi` | `materi_security_cat` | Nama collection vektor |
| `nama_embedding` | `paraphrase-multilingual-MiniLM-L12-v2` | Model embedding lokal |
| `jarak` | `cosine` | Metode jarak |
| `k` | `3` | Jumlah chunk yang diambil |
| `batas_jarak` | `0.7` | Batas jarak cosine — di atas ini dianggap tidak relevan |
| `model_llm` | `openai/gpt-oss-20b` | Model LLM di Groq |
| `temperature` | `0` | Deterministik |
| `max_tokens` | `2000` | Batas output |
| `system_prompt` | Jawab singkat dalam bahasa Indonesia… | System prompt |
| `pesan_tidak_ada` | Maaf, informasi tidak ditemukan di dokumen. | Balasan saat konteks tidak ditemukan |

Ubah nilai di file ini kalau perlu, lalu restart server.

---

## 4. Menyiapkan Data Pengetahuan

Index dibangun dari 4 PDF di folder `seed/`:

- `phishing.pdf` — Phishing Website Detection
- `mfa.pdf` — Multi-Factor Authentication (MFA)
- `sql-injection.pdf` — SQL Injection dan Mitigasinya
- `brute-force.pdf` — Brute Force dan Rate Limiting

Jalankan sekali (dengan virtualenv aktif):

```bash
python seed_documents.py
```

Skrip ini akan:
- Meng-ingest PDF di `seed/` yang belum ada (yang sudah ada otomatis dilewati),
- Menyimpan teks per-halaman ke `data/registry.sqlite`,
- Membuat chunk (70 kata, overlap 15) dan menyimpannya ke ChromaDB `data/vectordb`,
- Memperbarui `jumlah_dokumen` / `total_chunk` di `models/konfigurasi_rag.json`.

Kalau registry hilang/rusak tetapi teks masih ada, bangun ulang index dengan:

```bash
curl -X POST http://127.0.0.1:8001/reindex
```

---

## 5. Menjalankan Server

```bash
source .venv/Scripts/activate   # aktifkan virtualenv dulu
python app.py
```

Tampilan saat berhasil:

```
 * Serving Flask app 'app'
 * Debug mode: off
 * Running on http://127.0.0.1:8001
```

Hentikan dengan `Ctrl+C`.

> ⚠️ **Jalankan hanya SATU instance.** Windows mengizinkan beberapa proses memakai
> port yang sama, sehingga request bisa dijawab instance lama yang kodenya basi.
> Kalau ada dua kali `python app.py`, tutup semua lalu jalankan ulang sekali:
>
> ```bash
> netstat -ano | grep ":8001.*LISTENING"   # lihat PID yang memakai port
> taskkill //F //PID <pid>                 # tutup yang tidak diinginkan
> ```

---

## 6. Daftar Endpoint

Buka `GET /` untuk melihat daftar ini langsung dari server.

| Method | Endpoint | Fungsi |
|---|---|---|
| GET | `/` | Daftar endpoint (JSON) |
| GET | `/health` | Cek status service, jumlah dokumen & chunk |
| POST | `/chat` | Tanya jawab RAG |
| GET | `/documents` | Daftar dokumen terindeks |
| POST | `/documents` | Tambah & indeks dokumen teks baru |
| DELETE | `/documents/<id>` | Hapus dokumen beserta chunk-nya |
| POST | `/reindex` | Bangun ulang seluruh index vektor |

### GET `/health`

```bash
curl http://127.0.0.1:8001/health
```

```json
{
  "embedding": "paraphrase-multilingual-MiniLM-L12-v2",
  "kb_chunks": 20,
  "model_llm": "openai/gpt-oss-20b",
  "status": "ok"
}
```

### POST `/chat`

```bash
curl -X POST http://127.0.0.1:8001/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Apa itu phishing?"}'
```

Field opsional: `history` (list) untuk riwayat percakapan.

**Respons (200):**

```json
{
  "answer": "Phishing adalah upaya memperoleh kredensial ...",
  "sources": [
    {"id": "f674c16f...", "judul": "Phishing Website Detection", "halaman": 1}
  ],
  "status": "ok",
  "distance": 0.45
}
```

Kemungkinan nilai `status`:

| `status` | Arti |
|---|---|
| `ok` | Jawaban berhasil dihasilkan dari konteks dokumen |
| `not_found` | Tidak ada konteks relevan (di atas `batas_jarak`) — dijawab `pesan_tidak_ada` |
| `unsafe` | Pertanyaan terdeteksi sebagai permintaan serangan nyata — diblokir guard |
| `error` | Groq gagal (key invalid, gangguan jaringan) atau validasi input |

Validasi input mengembalikan **HTTP 422** (pertanyaan kosong, bukan string, atau
melebihi `MAX_QUESTION_LENGTH`).

### GET `/documents`

```bash
curl http://127.0.0.1:8001/documents
```

```json
{
  "documents": [
    {
      "id": "f674c16fb13e46c5866b5c8ab22298c6",
      "judul": "SQL Injection dan Mitigasinya",
      "sumber": "sql-injection.pdf",
      "chunk_count": 5,
      "status": "indexed",
      "indexed_at": "2026-10-19T16:04:01.725563+00:00"
    }
  ]
}
```

### POST `/documents`

```bash
curl -X POST http://127.0.0.1:8001/documents \
  -H "Content-Type: application/json" \
  -d '{"judul": "Pengenalan SIEM", "sumber": "catatan.md", "teks": "SIEM adalah ..."}'
```

Syarat: `judul`, `sumber`, `teks` wajib diisi dan `teks` minimal 20 karakter.
Respons **201**: `{"id": "...", "chunk_count": 8}`.

### DELETE `/documents/<id>`

```bash
curl -X DELETE http://127.0.0.1:8001/documents/f674c16fb13e46c5866b5c8ab22298c6
```

Respons: `{"deleted": true}` (atau `false` bila ID tidak ditemukan).

### POST `/reindex`

```bash
curl -X POST http://127.0.0.1:8001/reindex
```

Respons: `{"indexed": 4, "total_chunks": 20}`.

---

## 7. Menjalankan Test

```bash
source .venv/Scripts/activate
python test_rag.py
```

Ekspektasi akhir: **`Ran 8 tests` … `OK`**. Test mencakup:

- Guard `unsafe` memblokir sebelum retrieval/LLM,
- Gate `batas_jarak` melewati LLM saat tidak relevan,
- Deduplikasi `sources` per dokumen + halaman,
- Kegagalan Groq dipetakan menjadi `status: error` (bukan exception 500),
- Chunking dengan overlap,
- 404 path tak dikenal mengembalikan 404 (bukan "internal error"),
- Root `/` menampilkan daftar endpoint, `/health` tetap 200.

---

## 8. Troubleshooting

| Gejala | Penyebab | Solusi |
|---|---|---|
| `{"error":"AI service internal error."}` | Exception tak terduga di server | Cek traceback di terminal tempat `python app.py` berjalan (disimpan lewat `logging.exception`) |
| `{"error":"The requested URL was not found..."}` (404) | URL tidak ada — service ini API, bukan web | Buka `/` untuk melihat daftar endpoint; pastikan path persis `/health`, `/chat`, dll. |
| `{"answer":"AI sedang tidak tersedia...", "status":"error"}` di `/chat` | Groq menolak — umumnya `401 Invalid API Key` | Isi `GROQ_API_KEY` yang valid di `.env`, lalu **restart** server |
| Server tampak jalan tapi respons kadang pakai kode lama | Lebih dari satu instance `python app.py` di port 8001 | Tutup semua (lihat cara di bagian 5), jalankan satu saja |
| Pertama start lambat (~10–30 detik) | Model embedding diunduh/dimuat dari HuggingFace | Normal saat pertama kali; butuh internet, setelah itu dipakai dari cache lokal |
| Selalu `status: "not_found"` | Belum ada dokumen, atau jarak > `batas_jarak` (0.7) | Jalankan `python seed_documents.py`, cek `GET /health` (`kb_chunks` > 0), atau `POST /reindex` |
| Port 8001 sudah dipakai proses lain | Aplikasi lain memakai port | Ganti `PORT` di `.env`, atau tutup prosesnya (bagian 5) |
| `ModuleNotFoundError` | Virtualenv belum aktif / dependency belum terpasang | `source .venv/Scripts/activate` lalu `pip install -r requirements.txt` |

---

## 9. Struktur Proyek

```
.
├── app.py                  # Flask app — route & validasi HTTP
├── config.py               # Baca .env + models/konfigurasi_rag.json
├── rag.py                  # Pipeline RAG: retrieve → gate → augment → generate
├── seed_documents.py       # Ingest awal 4 PDF dari folder seed/
├── test_rag.py             # Unit test (unittest)
├── requirements.txt
├── .env.example            # Template konfigurasi (salin ke .env)
├── models/
│   └── konfigurasi_rag.json# Parameter pipeline RAG
├── seed/                   # 4 PDF materi
├── data/
│   ├── registry.sqlite     # Registry dokumen + teks per halaman
│   └── vectordb/           # ChromaDB
├── reference/              # Notebook referensi praktikum
└── PRD-Chat-AI-tutor.md    # Dokumen PRD
```

---

## 10. Alur Request `/chat`

```
Client (Laravel)
   │  POST /chat {"question": "..."}
   ▼
Validasi input (kosong / terlalu panjang → 422)
   │
   ▼
Guard unsafe  ── cocok pola serangan nyata ──► status "unsafe"
   │
   ▼
Embedding pertanyaan (lokal / API)
   │
   ▼
Retrieval ChromaDB (k=3, cosine)
   │
   ▼
Gate batas_jarak (0.7)  ── tidak relevan ──► status "not_found"
   │
   ▼
Augment prompt (template + konteks + riwayat)
   │
   ▼
Generate via Groq (openai/gpt-oss-20b)  ── gagal ──► status "error"
   │
   ▼
200 {"answer", "sources", "status": "ok", "distance"}
```
