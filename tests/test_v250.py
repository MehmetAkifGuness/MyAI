import tempfile
import unittest
from pathlib import Path

from boru.knowledge import (
    HybridKnowledgeRetriever,
    JsonKnowledgeRepository,
    KnowledgeCoordinator,
    KnowledgeService,
    RuleBasedKnowledgeRequestParser,
    SafeKnowledgeDocumentLoader,
    TextKnowledgeChunker,
)
from boru.memory import ConservativeMemoryDecisionGate
from boru.tools import ReadOnlyWorkspace


class FakeModel:
    def __init__(self):
        self.messages = []

    def generate(self, messages):
        self.messages.append(messages)
        return "Sistem PostgreSQL kullanır [1]."


class KnowledgeTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)
        self.index_path = self.root / "data" / "knowledge.json"
        self.model = FakeModel()
        self.service = KnowledgeService(
            repository=JsonKnowledgeRepository(self.index_path),
            loader=SafeKnowledgeDocumentLoader(
                ReadOnlyWorkspace(self.root, max_file_bytes=64 * 1024)
            ),
            chunker=TextKnowledgeChunker(max_characters=160, overlap_characters=20),
            retriever=HybridKnowledgeRetriever(),
        )
        self.coordinator = KnowledgeCoordinator(
            self.service,
            RuleBasedKnowledgeRequestParser(),
            self.model,
        )

    def tearDown(self):
        self.temp_directory.cleanup()

    def write_document(self, name="architecture.md", content=None):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            content
            or (
                "# Mimari\n\nBackend FastAPI kullanır. Veritabanı PostgreSQL'dir.\n"
                "Testler pytest ile çalıştırılır."
            ),
            encoding="utf-8",
        )
        return name


class KnowledgeServiceTests(KnowledgeTestCase):
    def test_indexes_updates_and_persists_document_chunks(self):
        source = self.write_document()

        self.assertEqual(self.service.add_source(source), "created")
        self.assertEqual(self.service.add_source(source), "unchanged")
        (self.root / source).write_text("Yeni bilgi: Redis kullanılır.", encoding="utf-8")
        self.assertEqual(self.service.add_source(source), "updated")

        reloaded = KnowledgeService(
            JsonKnowledgeRepository(self.index_path),
            SafeKnowledgeDocumentLoader(ReadOnlyWorkspace(self.root)),
            TextKnowledgeChunker(),
            HybridKnowledgeRetriever(),
        )
        self.assertEqual(reloaded.list_sources(), ((source, 1),))
        self.assertIn("Redis", reloaded.search("Redis")[0].chunk.text)

    def test_lexical_search_returns_source_and_line_metadata(self):
        source = self.write_document()
        self.service.add_source(source)

        hit = self.service.search("PostgreSQL", limit=1)[0]

        self.assertEqual(hit.source_path, source)
        self.assertGreaterEqual(hit.chunk.line_start, 1)
        self.assertIn("PostgreSQL", hit.chunk.text)

    def test_delete_source_removes_persisted_document(self):
        source = self.write_document()
        self.service.add_source(source)

        self.assertTrue(self.service.delete_source(source))
        self.assertFalse(self.service.delete_source(source))
        self.assertEqual(self.service.list_sources(), ())

    def test_loader_rejects_unsupported_sensitive_and_outside_sources(self):
        (self.root / "code.py").write_text("VALUE = 1", encoding="utf-8")
        self.write_document("secret.md", "token: sk-live-1234567890123456")

        with self.assertRaisesRegex(ValueError, "yalnızca"):
            self.service.add_source("code.py")
        with self.assertRaisesRegex(ValueError, "hassas"):
            self.service.add_source("secret.md")
        with self.assertRaises(RuntimeError):
            self.service.add_source("../outside.md")


class KnowledgeCoordinatorTests(KnowledgeTestCase):
    def test_add_list_search_and_grounded_answer_flow(self):
        source = self.write_document()

        added = self.coordinator.resolve(f"bilgi kaynağı ekle: {source}")
        listed = self.coordinator.resolve("bilgi kaynaklarını listele")
        searched = self.coordinator.resolve("bilgi ara: PostgreSQL")
        answered = self.coordinator.resolve(
            "bilgiye göre sor: Veritabanı olarak ne kullanılıyor?"
        )

        self.assertIn("eklendi", added or "")
        self.assertIn(source, listed or "")
        self.assertIn(f"{source}:", searched or "")
        self.assertIn("PostgreSQL kullanır [1]", answered or "")
        self.assertIn(f"[1] {source}:", answered or "")
        system_prompt = self.model.messages[0][0].content
        self.assertIn("GÜVENİLMEYEN BELGE VERİSİ", system_prompt)
        self.assertIn("PostgreSQL", system_prompt)

    def test_answer_does_not_call_model_without_retrieval_hit(self):
        response = self.coordinator.resolve("bilgiye göre sor: kuantum nedir?")

        self.assertIn("bulunamadı", response or "")
        self.assertEqual(self.model.messages, [])

    def test_unrelated_message_is_not_claimed(self):
        self.assertIsNone(self.coordinator.resolve("PostgreSQL nedir?"))

    def test_knowledge_commands_are_not_general_memory_candidates(self):
        gate = ConservativeMemoryDecisionGate()

        self.assertFalse(gate.should_evaluate("bilgi kaynağı ekle: docs/mimari.md"))
        self.assertFalse(gate.should_evaluate("bilgiye göre sor: mimari nedir?"))


class SemanticKnowledgeRetrieverTests(unittest.TestCase):
    def test_lexical_hit_skips_embedding_call(self):
        class UnexpectedEmbeddings:
            def embed(self, texts):
                raise AssertionError(texts)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "guide.md").write_text("PostgreSQL kullanılır.", encoding="utf-8")
            service = KnowledgeService(
                JsonKnowledgeRepository(root / "index.json"),
                SafeKnowledgeDocumentLoader(ReadOnlyWorkspace(root)),
                TextKnowledgeChunker(),
                HybridKnowledgeRetriever(UnexpectedEmbeddings()),
            )
            service.add_source("guide.md")

            hits = service.search("PostgreSQL")

        self.assertEqual(hits[0].source_path, "guide.md")

    def test_semantic_match_can_find_lexically_different_text(self):
        class Embeddings:
            def embed(self, texts):
                vectors = []
                for text in texts:
                    folded = text.casefold()
                    vectors.append([1.0, 0.0] if "depolama" in folded or "postgresql" in folded else [0.0, 1.0])
                return vectors

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "guide.md").write_text("PostgreSQL kullanılır.", encoding="utf-8")
            service = KnowledgeService(
                JsonKnowledgeRepository(root / "index.json"),
                SafeKnowledgeDocumentLoader(ReadOnlyWorkspace(root)),
                TextKnowledgeChunker(),
                HybridKnowledgeRetriever(Embeddings(), minimum_similarity=0.5),
            )
            service.add_source("guide.md")

            hits = service.search("Kalıcı depolama çözümü hangisi?")

        self.assertEqual(hits[0].source_path, "guide.md")


if __name__ == "__main__":
    unittest.main()
