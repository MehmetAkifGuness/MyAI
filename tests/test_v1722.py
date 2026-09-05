import unittest

from boru.architecture import ArchitectCoordinator, ArchitectureRequest, LLMArchitectAgent
from boru.performance import PerformanceMonitor
from boru.tools import EditSource, ProjectFileSelection


class UnexpectedModel:
    def generate_structured(self, messages, schema):
        raise AssertionError((messages, schema))


class Index:
    def list_editable_files(self):
        return ("parser.py", "models.py")


class Selector:
    def select_files(self, *, request, available_paths):
        del request
        return ProjectFileSelection(available_paths)


class Workspace:
    _CONTENT = {
        "parser.py": "class RequestParser:\n    def parse(self, text): ...\n",
        "models.py": "class CommandKind: ...\nclass CommandRequest: ...\n",
    }

    def read_edit_source(self, path):
        return EditSource(path, self._CONTENT[path], "hash")


class Validator:
    def validate_new_text_file(self, relative_path, content):
        del relative_path, content


class Parser:
    def parse(self, message):
        del message
        return ArchitectureRequest(
            "parser.py ve models.py içinde yeni güvenli komut türü için "
            "yalnızca bu iki dosyayı kapsayan plan hazırla",
            ("parser.py", "models.py"),
        )

    def is_architecture_intent(self, message):
        del message
        return True


class V1722FastScopedPlanTests(unittest.TestCase):
    def test_explicit_existing_scope_skips_model_and_builds_clean_plan(self):
        monitor = PerformanceMonitor()
        agent = LLMArchitectAgent(
            chat_model=UnexpectedModel(),
            file_index=Index(),
            file_selector=Selector(),
            workspace=Workspace(),
            creation_validator=Validator(),
            performance_monitor=monitor,
            fast_scoped_plans=True,
        )

        plan = agent.plan(Parser().parse("planla"))

        self.assertEqual(
            plan.summary,
            "Kaynak-temelli güvenli değişiklik planı: Yeni güvenli komut türü.",
        )
        self.assertIn("RequestParser", plan.steps[0].title)
        counters = dict(monitor.snapshot().counters)
        self.assertEqual(counters["architect.fast_scoped_plan"], 1)

    def test_render_separates_ordered_steps_from_following_sections(self):
        agent = LLMArchitectAgent(
            chat_model=UnexpectedModel(),
            file_index=Index(),
            file_selector=Selector(),
            workspace=Workspace(),
            creation_validator=Validator(),
            fast_scoped_plans=True,
        )
        response = ArchitectCoordinator(Parser(), agent).resolve("planla")

        self.assertIn("\n\nRiskler:\n", response)
        self.assertIn("\n\nTest stratejisi:\n", response)
        self.assertIn("\n\nMimari notlar:\n", response)


if __name__ == "__main__":
    unittest.main()
