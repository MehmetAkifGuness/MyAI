import re

from boru.tools.command_models import (
    CommandExecutionResult,
    CommandKind,
    TestSummary,
)


class TestOutputParser:
    def parse(self, result: CommandExecutionResult) -> TestSummary | None:
        if result.command.kind is CommandKind.UNITTEST:
            return self._parse_unittest(result)
        if result.command.kind is CommandKind.PYTEST:
            return self._parse_pytest(result)
        return None

    @staticmethod
    def _parse_unittest(result: CommandExecutionResult) -> TestSummary | None:
        total_match = re.search(r"Ran\s+(\d+)\s+tests?\s+in\b", result.output)
        if total_match is None:
            return None

        total = int(total_match.group(1))
        skipped = TestOutputParser._named_count(result.output, "skipped")
        failures = TestOutputParser._named_count(result.output, "failures")
        errors = TestOutputParser._named_count(result.output, "errors")
        failed = failures + errors
        if not result.succeeded and failed == 0:
            failed = None
            passed = None
        else:
            passed = max(total - failed - skipped, 0)

        return TestSummary(
            framework="unittest",
            total=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
        )

    @staticmethod
    def _parse_pytest(result: CommandExecutionResult) -> TestSummary | None:
        counts = {
            name: TestOutputParser._summary_count(result.output, name)
            for name in ("passed", "failed", "errors", "skipped")
        }
        if not any(value is not None for value in counts.values()):
            return None

        passed = counts["passed"] or 0
        failed = (counts["failed"] or 0) + (counts["errors"] or 0)
        skipped = counts["skipped"] or 0
        return TestSummary(
            framework="pytest",
            total=passed + failed + skipped,
            passed=passed,
            failed=failed,
            skipped=skipped,
        )

    @staticmethod
    def _named_count(output: str, name: str) -> int:
        match = re.search(rf"\b{name}=(\d+)\b", output)
        return int(match.group(1)) if match else 0

    @staticmethod
    def _summary_count(output: str, name: str) -> int | None:
        singular = name.removesuffix("s")
        matches = re.findall(rf"\b(\d+)\s+{singular}s?\b", output)
        return int(matches[-1]) if matches else None
