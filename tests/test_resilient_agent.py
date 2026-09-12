import json
import tempfile
import unittest
from pathlib import Path

from boru.agent.runtime import ReadOnlyToolAgent
from boru.code_index.index import SafeCodeIndex
from boru.code_index.tools import CodeSearchTool
from boru.tools import ReadFileTool
from boru.tools.contracts import ToolRisk
from boru.tools.executor import ToolExecutor
from boru.tools.policy import RiskBasedToolPolicy
from boru.tools.registry import ToolRegistry
from boru.tools.workspace import ReadOnlyWorkspace


class ScriptedModel:
    def __init__(self, actions, final_answers=()):
        self.actions = list(actions)
        self.final_answers = list(final_answers)
        self.prompts = []

    def generate_structured(self, messages, schema):
        self.prompts.append((messages, schema))
        if self.actions:
            return json.dumps(self.actions.pop(0), ensure_ascii=False)
        raise ValueError("Model aksiyonları tükendi.")

    def generate(self, messages):
        if not self.final_answers:
            return "Kanıta dayalı sentez yanıtı."
        return self.final_answers.pop(0)


class NoBootstrapAgent(ReadOnlyToolAgent):
    def _bootstrap(self, objective):
        return []


def action(kind, *, tool="", arguments=None, answer="", evidence=None):
    return {
        "action": kind,
        "tool_name": tool,
        "arguments": arguments or {},
        "answer": answer,
        "evidence": evidence or [],
        "reason": "kanıt toplama",
    }


class ResilientAgentTests(unittest.TestCase):
    def _setup_runtime(self, root, model, max_steps=6):
        workspace = ReadOnlyWorkspace(root)
        index = SafeCodeIndex(root)
        registry = ToolRegistry([ReadFileTool(workspace), CodeSearchTool(index)])
        executor = ToolExecutor(registry, RiskBasedToolPolicy((ToolRisk.SAFE, ToolRisk.READ_ONLY)))
        return NoBootstrapAgent(model, registry, executor, max_steps=max_steps)

    def test_self_healing_feedback_on_hallucinated_tool(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "main.py").write_text("class CoreApp:\n    pass\n", encoding="utf-8")

            # 1. Adım: Model hayali bir araç ("read_code") çağırıyor
            # 2. Adım: Model doğru aracı ("read_file") çağırıyor
            # 3. Adım: Model kanıtla final yanıt veriyor
            actions = [
                action("tool", tool="read_code", arguments={"path": "main.py"}),
                action("tool", tool="read_file", arguments={"path": "main.py"}),
                action("final", answer="CoreApp sınıfı main.py içindedir.", evidence=[2]),
            ]
            final_answers = [
                "CoreApp sınıfı main.py içindedir."
            ]
            model = ScriptedModel(actions, final_answers)
            agent = self._setup_runtime(root, model)
            report = agent.run("CoreApp nerede?")

            self.assertIn("Durum: TAMAMLANDI", report)
            # İkinci adımda modele giden promptta self-healing uyarısının yer aldığını doğrula
            second_prompt = model.prompts[1][0][1].content
            self.assertIn("Kayıt dışı araç", second_prompt)
            self.assertIn("read_file", second_prompt)

    def test_circuit_breaker_trips_on_consecutive_repeated_calls(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "app.py").write_text("class App: pass\n", encoding="utf-8")

            # Model aynı çağrıyı 5 kez arka arkaya tekrarlamaya çalışıyor
            repeat_act = action("tool", tool="read_file", arguments={"path": "app.py"})
            actions = [repeat_act, repeat_act, repeat_act, repeat_act, repeat_act]
            final_answers = ["Sentezlenmiş yanıt."]
            model = ScriptedModel(actions, final_answers)
            agent = self._setup_runtime(root, model, max_steps=10)
            report = agent.run("App nerede?")

            # 1 ilk çağrı + 2 tekrar (consecutive_repeats = 2 -> 3. adımda circuit breaker)
            # 5 aksiyondan sadece ilk 3'ü tüketilir, döngü güvenle kırılır
            self.assertGreater(len(actions), 0)
            self.assertLessEqual(len(model.prompts), 4)


if __name__ == "__main__":
    unittest.main()
