import ast
import re

from boru.tools.deterministic_edit import RequestedStateAlreadySatisfied
from boru.tools.edit_models import EditRequest
from boru.tools.project_edit_models import ProjectEditProposal, ProjectEditRequest


class DeterministicProjectEditNotApplicable(ValueError):
    pass


class RuleBasedStringAliasProjectEditPreparer:
    """Ground a quoted command-alias request in existing Python source and tests."""

    _REQUEST = re.compile(
        r"[\"“](?P<alias>[^\"”\r\n]{2,120})[\"”]\s+"
        r"(?:yazım(?:ı|ını)\s+)?[\"“](?P<canonical>[^\"”\r\n]{2,120})[\"”]\s+"
        r"(?:ile\s+aynı|gibi)\s+(?:kabul\s+et|çalışmalı|çalışsın)\b",
        re.I,
    )

    def __init__(self, workspace):
        self._workspace = workspace

    def prepare_project_edit(self, request: ProjectEditRequest) -> ProjectEditProposal:
        instruction = request.instruction.partition('\n\nDOĞRULAMA_KANITI:')[0].partition('\n\nARCHITECT_SUMMARY:')[0]
        match = self._REQUEST.search(instruction)
        if match is None:
            raise DeterministicProjectEditNotApplicable()
        alias = match.group("alias")
        canonical = match.group("canonical")
        if alias == canonical or not request.existing_file_scope:
            raise DeterministicProjectEditNotApplicable()

        edits = []
        satisfied = 0
        for path in request.existing_file_scope:
            source = self._workspace.read_edit_source(path)
            is_test = self._is_test(path)
            replacement = (
                self._test_replacement(source.content, alias, canonical)
                if is_test
                else self._source_replacement(source.content, alias, canonical)
            )
            if replacement is None:
                if (
                    self._test_is_satisfied(source.content, alias)
                    if is_test
                    else self._source_is_satisfied(source.content, alias, canonical)
                ):
                    satisfied += 1
                continue
            old_text, new_text = replacement
            edits.append(self._workspace.prepare_exact_replacement(
                EditRequest(path, old_text, new_text)
            ))
        if not edits and satisfied == len(request.existing_file_scope):
            raise RequestedStateAlreadySatisfied()
        if not edits:
            raise DeterministicProjectEditNotApplicable()
        return ProjectEditProposal(request.instruction, tuple(edits))

    @staticmethod
    def _source_replacement(content: str, alias: str, canonical: str):
        quoted = re.escape(canonical)
        pattern = re.compile(
            rf"^(?P<indent>[ \t]*)if (?P<value>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*) "
            rf"== (?P<literal>[\"']{quoted}[\"']):(?P<trailing>[ \t]*)(?P<cr>\r?)$",
            re.M,
        )
        matches = tuple(
            match for match in pattern.finditer(content)
            if match.group("literal")[0] == match.group("literal")[-1]
        )
        if len(matches) != 1:
            return None
        found = matches[0]
        old_text = found.group(0)
        quote = found.group("literal")[0]
        new_text = (
            f"{found.group('indent')}if {found.group('value')} in "
            f"{{{quote}{canonical}{quote}, {quote}{alias}{quote}}}:"
            f"{found.group('trailing')}{found.group('cr')}"
        )
        return old_text, new_text

    @staticmethod
    def _test_replacement(content: str, alias: str, canonical: str):
        if RuleBasedStringAliasProjectEditPreparer._test_is_satisfied(content, alias):
            return None
        pattern = re.compile(
            rf"\.resolve\(\s*(?P<quote>[\"']){re.escape(canonical)}(?P=quote)\s*\)"
        )
        matches = tuple(pattern.finditer(content))
        if not matches:
            return None
        found = matches[0]
        old_text = found.group(0)
        quote = found.group("quote")
        new_text = re.sub(
            rf"{re.escape(quote + canonical + quote)}",
            lambda _match: quote + alias + quote,
            old_text,
            count=1,
        )
        return old_text, new_text

    @staticmethod
    def _source_is_satisfied(content: str, alias: str, canonical: str) -> bool:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return False
        required = {alias, canonical}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare) or not any(
                isinstance(operator, ast.In) for operator in node.ops
            ):
                continue
            for comparator in node.comparators:
                if not isinstance(comparator, (ast.Set, ast.List, ast.Tuple)):
                    continue
                values = {
                    item.value
                    for item in comparator.elts
                    if isinstance(item, ast.Constant) and isinstance(item.value, str)
                }
                if required <= values:
                    return True
        return False

    @staticmethod
    def _test_is_satisfied(content: str, alias: str) -> bool:
        return re.search(
            rf"\.resolve\(\s*([\"']){re.escape(alias)}\1\s*\)", content
        ) is not None

    @staticmethod
    def _is_test(path: str) -> bool:
        folded = path.replace("\\", "/").casefold()
        name = folded.rsplit("/", 1)[-1]
        return folded.startswith("tests/") or "/tests/" in folded or name.startswith("test_") or "_test." in name


class FallbackProjectEditProposalPreparer:
    def __init__(self, primary, fallback):
        self._primary = primary
        self._fallback = fallback

    def prepare_project_edit(self, request: ProjectEditRequest) -> ProjectEditProposal:
        try:
            return self._primary.prepare_project_edit(request)
        except DeterministicProjectEditNotApplicable:
            return self._fallback.prepare_project_edit(request)
