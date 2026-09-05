import unittest

from boru.architecture import ArchitectureRequest, LLMArchitectAgent
from boru.models import ChatMessage
from boru.ollama_model import OllamaChatModel
from boru.performance import PerformanceMonitor
from boru.tools import EditSource, ProjectFileSelection


class TimeoutModel:
    def __init__(self):
        self.calls = 0

    def generate_structured(self, messages, schema):
        del messages, schema
        self.calls += 1
        raise TimeoutError("timed out")


class InvalidOutputModel:
    def __init__(self):
        self.calls = 0

    def generate_structured(self, messages, schema):
        del messages, schema
        self.calls += 1
        return '{"summary":"eksik"}'


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


class ArchitectTimeoutFallbackTests(unittest.TestCase):
    @staticmethod
    def _agent(model, monitor, *, max_attempts=3):
        return LLMArchitectAgent(
            chat_model=model,
            file_index=Index(),
            file_selector=Selector(),
            workspace=Workspace(),
            creation_validator=Validator(),
            performance_monitor=monitor,
            max_attempts=max_attempts,
        )

    def test_timeout_returns_grounded_plan_without_retry(self):
        model = TimeoutModel()
        monitor = PerformanceMonitor()
        agent = self._agent(model, monitor)

        result = agent.plan(
            ArchitectureRequest("güvenli komut ekle", ("parser.py", "models.py"))
        )

        self.assertEqual(model.calls, 1)
        self.assertEqual(result.existing_files, ("parser.py", "models.py"))
        self.assertIn("RequestParser", result.steps[0].title)
        counters = dict(monitor.snapshot().counters)
        self.assertEqual(counters["architect.fallback.timeout"], 1)

    def test_final_schema_error_returns_grounded_plan(self):
        model = InvalidOutputModel()
        monitor = PerformanceMonitor()
        agent = self._agent(model, monitor, max_attempts=1)

        result = agent.plan(
            ArchitectureRequest("güvenli komut ekle", ("parser.py", "models.py"))
        )

        self.assertEqual(model.calls, 1)
        self.assertIn("RequestParser", result.steps[0].title)
        counters = dict(monitor.snapshot().counters)
        self.assertEqual(counters["architect.fallback.invalid_output"], 1)

    def test_structured_generation_uses_bounded_deterministic_options(self):
        normal_calls = []
        structured_calls = []

        def normal_client(**kwargs):
            normal_calls.append(kwargs)
            return {"message": {"content": "normal"}}

        def structured_client(**kwargs):
            structured_calls.append(kwargs)
            return {"message": {"content": "{}"}}

        model = OllamaChatModel(
            "test",
            chat_client=normal_client,
            structured_chat_client=structured_client,
            structured_num_predict=256,
        )

        result = model.generate_structured(
            [ChatMessage("user", "planla")],
            {"type": "object"},
        )

        self.assertEqual(result, "{}")
        self.assertEqual(normal_calls, [])
        self.assertEqual(
            structured_calls[0]["options"],
            {"temperature": 0, "num_predict": 256},
        )


if __name__ == "__main__":
    unittest.main()
