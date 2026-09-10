import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

import main_v170
from boru.benchmark.cases import catalog
from boru.benchmark.coordinator import BenchmarkCoordinator
from boru.benchmark.runner import CodingBenchmark
from boru.coding.models import CodingRequest, CodingSession
from boru.coding.staged_repair import StagedValidationRepair
from boru.coding.staged_applier import StagedCodingApplier
from boru.evaluation.models import Check, EvaluationReport, Verdict
from boru.evaluation.service import EvidenceEvaluator
from boru.modeling import StructuredModelCascade
from boru.modeling.task_routing import TaskModelRouter
from boru.repository.evidence import TaskEvidence
from boru.repository.experience import VerifiedTaskExperience
from boru.repository.investigation import InvestigatingTaskAnalyzer
from boru.repository.workspace import build_repository_workspace, RepositoryWorkspaceRuntime
from boru.release import build_release
from boru.tools.deterministic_edit import RequestedStateAlreadySatisfied
from boru.tools.deterministic_project_edit import RuleBasedStringAliasProjectEditPreparer
from boru.tools import SafeEditWorkspace
from boru.tools.project_edit_models import ProjectEditRequest, ProjectEditProposal
from boru.tools.edit_models import EditRequest
from boru.ollama_model import OllamaChatModel
from boru.models import ChatMessage
from tests.test_v1000 import TestOnlyExecutor
from tests.test_v180 import edit_proposal, Architect, architecture_plan, coordinator


def reply(action='finish', **fields):
    return json.dumps(dict(action=action, path='', start=1, diagnosis='', edit_paths=[],
                           test_paths=[], citations=[], question='') | fields)


def fixture(root):
    (root / 'maths.py').write_text('def add(a, b):\n    return a - b\n', encoding='utf-8')
    (root / 'test_maths.py').write_text(
        'import unittest\nfrom maths import add\n\nclass Maths(unittest.TestCase):\n'
        '    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n', encoding='utf-8')


def finish():
    return reply(diagnosis='Toplama yerine çıkarma yapılıyor.', edit_paths=['maths.py'],
                 test_paths=['test_maths.py'], citations=[dict(path='maths.py', line=2, quote='return a - b')])


class InvestigationTests(unittest.TestCase):
    def test_discovered_read_tests_fill_empty_model_verification_list(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root)
            data = json.loads(finish())
            data['test_paths'] = []
            model = Mock(generate_structured=Mock(return_value=json.dumps(data)))
            brief = InvestigatingTaskAnalyzer(TaskModelRouter(model), Mock()).analyze(root, 'maths.py düzelt')
            self.assertEqual(brief.test_paths, ('test_maths.py',))

    def test_transport_error_retries_with_secondary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root)
            primary = Mock(generate_structured=Mock(side_effect=Exception('transport failed')))
            fallback = Mock(generate_structured=Mock(return_value=finish()))
            analyzer = InvestigatingTaskAnalyzer(TaskModelRouter(StructuredModelCascade(primary, fallback)), Mock())
            self.assertEqual(analyzer.analyze(root, 'maths.py düzelt').edit_paths, ('maths.py',))
            primary.generate_structured.assert_called_once()
            fallback.generate_structured.assert_called_once()

    def test_model_can_read_later_source_window(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'long.py').write_text('# context\n' * 200 + 'VALUE = 1\n')
            final = reply(diagnosis='Değer satırı 201.', edit_paths=['long.py'],
                          citations=[dict(path='long.py', line=201, quote='VALUE = 1')])
            model = Mock(generate_structured=Mock(side_effect=[reply('read', path='long.py', start=161), final]))
            brief = InvestigatingTaskAnalyzer(TaskModelRouter(model), Mock()).analyze(root, 'long.py VALUE değerini 2 yap')
            self.assertIn('201', brief.evidence_context)

    def test_explicit_test_cannot_be_dropped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root)
            invalid = json.loads(finish())
            invalid['test_paths'] = []
            model = Mock(generate_structured=Mock(return_value=json.dumps(invalid)))
            with self.assertRaisesRegex(ValueError, 'testler'):
                InvestigatingTaskAnalyzer(TaskModelRouter(model), Mock(), max_steps=1).analyze(root, 'maths.py düzelt test_maths.py ile doğrula')

    def test_source_and_test_loop_produces_grounded_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root)
            model = Mock(generate_structured=Mock(side_effect=[reply('test'), finish()]))
            evaluator = EvidenceEvaluator(root, TestOnlyExecutor(root, 'test'))
            analyzer = InvestigatingTaskAnalyzer(TaskModelRouter(model), evaluator)
            brief = analyzer.analyze(root, 'maths.py toplama hatasını düzelt', run_tests=True)
            self.assertEqual(brief.edit_paths, ('maths.py',))
            self.assertEqual(brief.test_paths, ('test_maths.py',))
            self.assertIn('AssertionError', brief.evidence_context)
            self.assertEqual(evaluator.latest.verdict, Verdict.FAIL)
            self.assertIn('a - b', (root / 'maths.py').read_text())

    def test_fabricated_citation_is_rejected_with_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root)
            bad = finish().replace('return a - b', 'return a * b')
            model = Mock(generate_structured=Mock(side_effect=[bad, finish()]))
            analyzer = InvestigatingTaskAnalyzer(TaskModelRouter(model), Mock())
            self.assertTrue(analyzer.analyze(root, 'maths.py hatasını düzelt').edit_paths)
            payload = json.loads(model.generate_structured.call_args.args[0][1].content)
            self.assertIn('Alıntı', payload['validation_errors'][0])

    def test_explanation_cannot_execute_test(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root)
            evaluator = Mock()
            model = Mock(generate_structured=Mock(side_effect=[reply('test'), finish()]))
            InvestigatingTaskAnalyzer(TaskModelRouter(model), evaluator).analyze(root, 'maths.py incele')
            evaluator.evaluate.assert_not_called()

    def test_test_rewrite_and_scope_escape_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root)
            for paths in (['test_maths.py'], ['../escape.py']):
                with self.subTest(paths=paths):
                    data = json.loads(finish())
                    data['edit_paths'] = paths
                    model = Mock(generate_structured=Mock(return_value=json.dumps(data)))
                    with self.assertRaises(ValueError):
                        InvestigatingTaskAnalyzer(TaskModelRouter(model), Mock(), max_steps=1).analyze(root, 'maths.py düzelt')

    def test_missing_explicit_path_never_becomes_partial_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root)
            with self.assertRaisesRegex(ValueError, 'manifest'):
                TaskEvidence(root, 'missing.py ve test_maths.py düzelt')

    def test_windows_read_more_and_detect_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root)
            evidence = TaskEvidence(root, 'maths.py')
            evidence.read('maths.py')
            with self.assertRaises(ValueError):
                evidence.read('../maths.py')
            (root / 'maths.py').write_text('VALUE = 2\n')
            with self.assertRaisesRegex(ValueError, 'değişti'):
                evidence.assert_current()

    def test_v12_workspace_keeps_changes_pending_until_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root)
            model = Mock(generate_structured=Mock(return_value=finish()))
            with patch('boru.repository.workspace.DockerSandboxExecutor', TestOnlyExecutor):
                runtime = build_repository_workspace(root, model, 'test', True, True, root / 'data/experience')
                brief = runtime.analyze_task('maths.py toplama hatasını düzelt')
                runtime.coding._proposal_preparer = Mock(prepare_project_edit=Mock(return_value=(
                    ProjectEditProposal(
                        'fix', (SafeEditWorkspace(root).prepare_exact_replacement(
                            EditRequest('maths.py', 'a - b', 'a + b')
                        ),)
                    )
                )))
                result = runtime.resolve_coding('kodla: toplama hatasını düzelt\nBORU_DOSYA_KAPSAMI: maths.py', brief=brief)
                self.assertIn('ONAY', result.upper())
                self.assertIn('a - b', (root / 'maths.py').read_text())
                result = runtime.resolve_coding('kod değişikliğini onayla')
                self.assertIn('uygulandı', result)
                self.assertIn('a + b', (root / 'maths.py').read_text())
                self.assertEqual(len(runtime.experience.read()), 1)


class ExperienceAndRoutingTests(unittest.TestCase):
    def test_noop_still_validates_explicit_research_tests(self):
        coding, _, _, applier = coordinator()
        applier.validation_paths = ('checks/test_extra.py',)
        evaluator = Mock(validate_paths=Mock(return_value='verified'))
        coding._quality_evaluator = evaluator
        coding._render_already_satisfied(architecture_plan())
        evaluator.validate_paths.assert_called_once_with(('a.py', 'checks/test_extra.py'))

    def test_plain_coding_does_not_inherit_previous_investigation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root)
            model = Mock(generate_structured=Mock(return_value=finish()))
            analyzer = InvestigatingTaskAnalyzer(TaskModelRouter(model), Mock())
            brief = analyzer.analyze(root, 'maths.py düzelt')
            applier = StagedCodingApplier(root, Mock(), Mock())
            runtime = RepositoryWorkspaceRuntime(root, Mock(), Mock(), None, applier, analyzer)
            runtime.resolve_coding('kodla: ilk görev', brief=brief)
            self.assertTrue(applier.context_fingerprints)
            runtime.resolve_coding('kodla: başka görev')
            self.assertEqual(applier.context_fingerprints, ())
            self.assertEqual(applier.validation_paths, ())

    def test_unread_source_is_not_registered_as_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'long.py').write_text('#' * 7000)
            evidence = TaskEvidence(root, 'long.py')
            for start in (2, 1):
                with self.assertRaises(ValueError):
                    evidence.read('long.py', start)
            self.assertEqual(evidence.fingerprints, {})

    def test_qwen_structured_thinking_setting_does_not_affect_chat(self):
        client = Mock(return_value={'message': {'content': '{}'}})
        model = OllamaChatModel('qwen3.5:9b', chat_client=client, structured_thinking=False)
        model.generate_structured([ChatMessage('user', 'test')], {'type': 'object'})
        self.assertIs(client.call_args.kwargs['think'], False)
        model.generate([ChatMessage('user', 'test')])
        self.assertNotIn('think', client.call_args.kwargs)

    def test_research_source_drift_blocks_before_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root)
            proposal = ProjectEditProposal('fix', (SafeEditWorkspace(root).prepare_exact_replacement(
                EditRequest('maths.py', 'a - b', 'a + b')
            ),))
            applier = StagedCodingApplier(root, Mock(), Mock())
            reader = TaskEvidence(root, 'maths.py')
            reader.read('test_maths.py')
            applier.context_fingerprints = tuple(reader.fingerprints.items())
            (root / 'test_maths.py').write_text('CHANGED = 1\n')
            with self.assertRaisesRegex(ValueError, 'kanıt dosyası değişti'):
                applier.apply_project_edit(proposal)
            self.assertIn('a - b', (root / 'maths.py').read_text())

    def test_verified_memory_is_repo_scoped_and_invalidated_by_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root)
            storage = root / 'data/experience.json'
            service = VerifiedTaskExperience(root, storage)
            digest = hashlib.sha256((root / 'maths.py').read_bytes()).hexdigest()
            report = EvaluationReport(('maths.py',), (('maths.py', digest),), (Check('Test', Verdict.PASS, 'ok'),))
            evaluator = Mock(is_current=Mock(return_value=True))
            self.assertFalse(service.record(replace(report, checks=(Check('Test', Verdict.UNKNOWN, ''),)), evaluator))
            self.assertTrue(service.record(report, evaluator))
            self.assertTrue(service.recall(('maths.py',)))
            (root / 'maths.py').write_text('VALUE = 3\n')
            self.assertFalse(service.recall(('maths.py',)))
            other = root / 'other'
            other.mkdir()
            self.assertEqual(VerifiedTaskExperience(other, storage).read(), [])

    def test_routing_uses_configured_secondary_for_multiple_files(self):
        primary, secondary = object(), object()
        router = TaskModelRouter(StructuredModelCascade(primary, secondary))
        self.assertIs(router.for_task('küçük değişiklik').primary, primary)
        self.assertIs(router.for_task('iki dosya', 2).primary, secondary)

    def test_actual_turkish_alias_prompt_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'coordinator.py').write_text('if normalized in {"benchmark durumu", "benchmark durum"}:\n    pass\n')
            (root / 'test_coordinator.py').write_text('status = coordinator.resolve("benchmark durum")\n')
            with self.assertRaises(RequestedStateAlreadySatisfied):
                RuleBasedStringAliasProjectEditPreparer(SafeEditWorkspace(root)).prepare_project_edit(ProjectEditRequest(
                    '"benchmark durum" yazımı "benchmark durumu" ile aynı çalışmalı; test_coordinator.py ile doğrula',
                    ('coordinator.py', 'test_coordinator.py'), (),
                ))

    def test_repair_has_failed_candidate_and_rejects_identical_patch(self):
        proposal = edit_proposal()
        session = CodingSession(Mock(), Architect().plan(Mock()), proposal)
        preparer = Mock(prepare_project_edit=Mock(return_value=proposal))
        repair = StagedValidationRepair(preparer, max_attempts=2)
        repair.reset()
        report = EvaluationReport(('a.py',), (), (Check('Test', Verdict.FAIL, 'wrong value'),))
        with self.assertRaisesRegex(ValueError, 'tekrarlandı'):
            repair.prepare(session, report)
        self.assertIn('FAILED_CANDIDATE', preparer.prepare_project_edit.call_args.args[0].instruction)

    def test_v12_release_enables_bundle(self):
        with patch.object(main_v170, 'build_application') as builder:
            build_release('V12.0')
            self.assertEqual(builder.call_args.kwargs['application_version'], 'V12.0')
            self.assertTrue(builder.call_args.kwargs['deep_reasoning_enabled'])
            build_release('V11.0')
            self.assertFalse(builder.call_args.kwargs['deep_reasoning_enabled'])


class RepositoryBenchmarkTests(unittest.TestCase):
    def test_partial_repair_preserves_candidate_and_dependency_context(self):
        case = catalog('repo')[-1]
        parse_source = ('def boolean(text):\n    value = text.casefold()\n'
                        '    if value not in {"true", "false"}:\n        raise ValueError("debug")\n'
                        '    return value == "true"\n')
        settings_source = ('from app.parse import boolean\n\ndef parse_config(data):\n'
                           '    timeout = int(data.get("timeout", 30))\n'
                           '    if timeout <= 0:\n        raise ValueError("timeout")\n'
                           '    return {"debug": boolean(data.get("debug", "false")), "timeout": timeout}\n')
        responses = [json.dumps(dict(action='edit', question='', files=[dict(path=p, content=s)]))
                     for p, s in [('app/parse.py', parse_source), ('app/settings.py', settings_source)]]
        model = Mock(generate_structured=Mock(side_effect=responses))
        report = CodingBenchmark(lambda root: TestOnlyExecutor(root, 'test')).run({'scripted': model}, (case,))
        self.assertEqual(report['summary']['scripted']['coding_passed'], 1)
        self.assertEqual(report['summary']['scripted']['recovered_count'], 1)
        feedback = json.loads(model.generate_structured.call_args.args[0][1].content)
        self.assertEqual(feedback['files']['app/parse.py'], parse_source)
        self.assertIn('app/settings.py', feedback['files'])

    def test_nested_fixture_has_independent_acceptance_checks(self):
        cases = catalog('repo')
        self.assertEqual(len(cases), 5)
        model = Mock(generate_structured=Mock(return_value=json.dumps(dict(action='edit', question='', files=[{
            'path': 'app/commands.py',
            'content': 'from app.normalize import normalize\n\ndef resolve(text):\n'
                       '    return "ready" if normalize(text) in {"benchmark durum", "benchmark durumu"} else None\n',
        }]))))
        report = CodingBenchmark(lambda root: TestOnlyExecutor(root, 'test')).run({'scripted': model}, cases[:1])
        self.assertEqual(report['summary']['scripted']['coding_passed'], 1)
        self.assertNotIn('assertEqual', model.generate_structured.call_args.args[0][1].content)
        for case in cases:
            for path, source in case.sources:
                compile(source, path, 'exec')

    def test_repo_suite_command_and_cli_are_equivalent(self):
        native = BenchmarkCoordinator._parse('benchmark çalıştır: model | paket=repo | limit=5')
        cli = BenchmarkCoordinator._parse('python -B -m boru.benchmark --model model --suite repo --limit 5')
        self.assertEqual(native, cli)
