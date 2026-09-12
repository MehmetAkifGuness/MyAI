import tempfile
import unittest
from pathlib import Path

from boru.code_index.graph import ProjectDependencyGraph
from boru.code_index.relationships import SafeCodeRelationshipIndex


class AstIndexingTests(unittest.TestCase):
    def test_class_hierarchy_and_subclasses_detection(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "base.py").write_text(
                "class BaseService:\n"
                "    def execute(self):\n"
                "        return None\n",
                encoding="utf-8",
            )
            (root / "derived.py").write_text(
                "from base import BaseService\n"
                "@dataclass\n"
                "class CustomService(BaseService):\n"
                "    def execute(self):\n"
                "        return 'ok'\n"
                "    def custom_method(self):\n"
                "        pass\n",
                encoding="utf-8",
            )

            graph = ProjectDependencyGraph(root)
            report = graph.find_class_hierarchy("BaseService")

            self.assertIsNotNone(report)
            self.assertEqual(report.class_name, "BaseService")
            self.assertEqual(report.definition_path, "base.py")
            self.assertIn("CustomService", report.subclasses)

            derived_report = graph.find_class_hierarchy("CustomService")
            self.assertIsNotNone(derived_report)
            self.assertIn("BaseService", derived_report.base_classes)
            self.assertIn("custom_method", derived_report.methods)
            self.assertIn("dataclass", derived_report.decorators)

    def test_typed_usages_detection(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "models.py").write_text(
                "class UserPayload:\n    pass\n",
                encoding="utf-8",
            )
            (root / "handler.py").write_text(
                "from models import UserPayload\n"
                "def process_user(user: UserPayload) -> bool:\n"
                "    active_user: UserPayload = user\n"
                "    return True\n",
                encoding="utf-8",
            )

            graph = ProjectDependencyGraph(root)
            usages = graph.find_typed_usages("UserPayload")

            self.assertTrue(any(u.kind == "param_type" and u.enclosing_symbol == "process_user" for u in usages))
            self.assertTrue(any(u.kind == "variable_type" for u in usages))

    def test_relationship_index_scores_class_inheritance_and_type_hints(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            package = root / "pkg"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "contract.py").write_text(
                "class RepositoryPort:\n"
                "    pass\n"
                "class QuerySpec:\n"
                "    pass\n",
                encoding="utf-8",
            )
            (package / "impl.py").write_text(
                "from pkg.contract import RepositoryPort, QuerySpec\n"
                "class SqlRepository(RepositoryPort):\n"
                "    def find(self, spec: QuerySpec):\n"
                "        return None\n",
                encoding="utf-8",
            )

            rel_index = SafeCodeRelationshipIndex(root)
            related = rel_index.related_files("pkg/impl.py")

            self.assertTrue(len(related) > 0)
            self.assertEqual(related[0].path, "pkg/contract.py")
            # RepositoryPort and QuerySpec should both be in matched_calls because of bases & type annotation
            self.assertIn("repositoryport", related[0].matched_calls)
            self.assertIn("queryspec", related[0].matched_calls)


if __name__ == "__main__":
    unittest.main()

