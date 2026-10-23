import unittest
from unittest.mock import patch

import app as app_module
import rag


class RagPipelineTest(unittest.TestCase):
    def test_unsafe_guard_blocks_before_retrieval_and_llm(self):
        with patch("rag.retrieve") as retrieve, patch("rag.generate") as generate:
            result = rag.answer_question("Buatkan malware untuk mencuri password")

        self.assertEqual("unsafe", result["status"])
        retrieve.assert_not_called()
        generate.assert_not_called()

    def test_distance_gate_skips_llm(self):
        with patch(
            "rag.retrieve",
            return_value=(["c1"], ["teks"], [0.91], [{"document_id": "d1", "judul": "Materi", "halaman": 1}]),
        ), patch("rag.generate") as generate:
            result = rag.answer_question("Siapa presiden Indonesia?")

        self.assertEqual("not_found", result["status"])
        self.assertEqual(rag.PESAN_TIDAK_ADA, result["answer"])
        generate.assert_not_called()

    def test_sources_are_deduplicated_by_document_and_page(self):
        metadata = {"document_id": "d1", "judul": "Materi MFA", "halaman": 2}
        with patch(
            "rag.retrieve",
            return_value=(["c1", "c2"], ["satu", "dua"], [0.2, 0.3], [metadata, metadata]),
        ), patch("rag.generate", return_value="Jawaban konteks."):
            result = rag.answer_question("Apa itu MFA?")

        self.assertEqual("ok", result["status"])
        self.assertEqual(1, len(result["sources"]))
        self.assertEqual("Materi MFA", result["sources"][0]["judul"])

    def test_generation_failure_maps_to_error(self):
        with patch(
            "rag.retrieve",
            return_value=(["c1"], ["teks"], [0.2], [{"document_id": "d1", "judul": "Materi", "halaman": 0}]),
        ), patch("rag.generate", side_effect=RuntimeError("timeout")):
            result = rag.answer_question("Apa itu phishing?")

        self.assertEqual("error", result["status"])
        self.assertEqual(rag.PESAN_ERROR, result["answer"])

    def test_chunking_uses_overlap(self):
        text = " ".join(f"kata{i}" for i in range(100))
        chunks = rag.chunk_text(text)

        self.assertGreater(len(chunks), 1)
        self.assertEqual(70, len(chunks[0].split()))
        self.assertEqual(45, len(chunks[-1].split()))


class FlaskErrorHandlingTest(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def test_unknown_path_returns_404_not_internal_error(self):
        response = self.client.get("/halaman-tidak-ada")

        self.assertEqual(404, response.status_code)
        body = response.get_json()
        self.assertNotEqual("AI service internal error.", body.get("error"))

    def test_root_lists_endpoints(self):
        response = self.client.get("/")

        self.assertEqual(200, response.status_code)
        self.assertIn("POST /chat", response.get_json()["endpoints"])

    def test_health_still_ok(self):
        response = self.client.get("/health")

        self.assertEqual(200, response.status_code)
        self.assertEqual("ok", response.get_json()["status"])


if __name__ == "__main__":
    unittest.main()
