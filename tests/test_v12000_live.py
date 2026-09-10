"""Opt-in real Ollama + Docker checks. Never run generated code on the host."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from boru.benchmark.cases import catalog
from boru.benchmark.runner import CodingBenchmark
from boru.evaluation.service import EvidenceEvaluator
from boru.modeling import StructuredModelCascade
from boru.modeling.task_routing import TaskModelRouter
from boru.ollama_model import OllamaChatModel
from boru.repository.investigation import InvestigatingTaskAnalyzer
from boru.sandbox import DockerSandboxExecutor
from tests.test_v12000 import fixture


@unittest.skipUnless(os.getenv('BORU_LIVE_V12') == '1', 'Ollama ve Docker canlı testi isteğe bağlı')
class LiveIntelligenceTests(unittest.TestCase):
    def test_research_on_real_model(self):
        primary = OllamaChatModel('qwen2.5-coder:7b', structured_timeout_seconds=60, structured_num_predict=1800)
        secondary = OllamaChatModel('qwen3.5:9b', structured_timeout_seconds=60, structured_num_predict=1800, structured_thinking=False)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root)
            analyzer = InvestigatingTaskAnalyzer(
                TaskModelRouter(StructuredModelCascade(primary, secondary)),
                EvidenceEvaluator(root, DockerSandboxExecutor(root)),
            )
            try:
                brief = analyzer.analyze(root, 'maths.py add fonksiyonu toplama yapmalı; çıkarma hatasını düzelt', run_tests=True)
            finally:
                print('\nV12_RESEARCH_TRACE=' + json.dumps(analyzer.trace, ensure_ascii=True), flush=True)
            self.assertEqual(brief.edit_paths, ('maths.py',))
            self.assertTrue(brief.diagnosis)
            self.assertIn('a - b', (root / 'maths.py').read_text())

    def test_repository_benchmark_measurement(self):
        model = OllamaChatModel('qwen2.5-coder:7b', structured_timeout_seconds=60, structured_num_predict=2048)
        fallback = OllamaChatModel('qwen3.5:9b', structured_timeout_seconds=60, structured_num_predict=2048, structured_thinking=False)
        report = CodingBenchmark(DockerSandboxExecutor).run(
            {'qwen2.5-coder:7b': model}, catalog('repo'), budget_seconds=900,
            fallback_model=('qwen3.5:9b', fallback),
        )
        output = Path(__file__).resolve().parents[1] / 'data/benchmarks' / ('v12-' + uuid4().hex + '.json')
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
        print('\nV12_LIVE_REPORT=' + str(output), flush=True)
        print(json.dumps(report['summary'], ensure_ascii=True), flush=True)
        self.assertEqual(report['state'], 'completed')
        self.assertEqual(report['progress']['completed'], 5)
