import re
from pathlib import Path

from boru.agent.models import AgentObservation
from boru.tools.contracts import ToolExecutorPort, ToolRegistryPort
from boru.tools.models import ToolCall, ToolResult


class DeterministicEvidenceBootstrapper:
    """Kod hedefinden ilk arama ve kaynak okuma kanıtlarını deterministik üretir."""

    def __init__(self, registry: ToolRegistryPort, executor: ToolExecutorPort) -> None:
        self._registry = registry
        self._executor = executor

    def build(self, objective: str) -> list[AgentObservation]:
        query = self._query(objective)
        if not query or self._registry.get("search_code") is None:
            return []
        search_arguments: dict[str, object] = {"query": query, "max_results": 8}
        search_result = self._executor.execute(
            ToolCall(tool_name="search_code", arguments=search_arguments)
        )
        observations = [
            AgentObservation(
                step=1,
                tool_name="search_code",
                arguments=search_arguments,
                result=search_result,
            )
        ]
        source_path = self._first_path(search_result)
        if source_path is None or self._registry.get("read_file") is None:
            return observations
        read_arguments: dict[str, object] = {"path": source_path}
        observations.append(
            AgentObservation(
                step=2,
                tool_name="read_file",
                arguments=read_arguments,
                result=self._executor.execute(
                    ToolCall(tool_name="read_file", arguments=read_arguments)
                ),
            )
        )
        self._append_targeted_test_evidence(observations, source_path, objective)
        self._append_related_evidence(observations, source_path, objective)
        self._append_impact_evidence(observations, source_path, objective)
        return observations

    def _append_targeted_test_evidence(
        self,
        observations: list[AgentObservation],
        source_path: str,
        objective: str,
    ) -> None:
        folded = objective.casefold()
        if (
            self._registry.get("run_targeted_test") is None
            or "test" not in folded
            or not any(cue in folded for cue in ("çalıştır", "calistir", "koş", "run", "sandbox"))
        ):
            return
        targets = self._test_paths(objective) or (source_path,)
        for target in targets:
            arguments: dict[str, object] = {
                "path": target,
                "runner": "pytest" if "pytest" in folded else "unittest",
            }
            observations.append(
                AgentObservation(
                    step=len(observations) + 1,
                    tool_name="run_targeted_test",
                    arguments=arguments,
                    result=self._executor.execute(
                        ToolCall(tool_name="run_targeted_test", arguments=arguments)
                    ),
                )
            )

    def _append_impact_evidence(
        self,
        observations: list[AgentObservation],
        source_path: str,
        objective: str,
    ) -> None:
        folded = objective.casefold()
        if (
            self._registry.get("impact_analysis") is None
            or not any(cue in folded for cue in ("etkilen", "etki", "kim kullan", "nereden çağr"))
        ):
            return
        arguments: dict[str, object] = {
            "path": source_path,
            "max_depth": 3,
            "max_results": 20,
        }
        observations.append(
            AgentObservation(
                step=len(observations) + 1,
                tool_name="impact_analysis",
                arguments=arguments,
                result=self._executor.execute(
                    ToolCall(tool_name="impact_analysis", arguments=arguments)
                ),
            )
        )

    def _append_related_evidence(
        self,
        observations: list[AgentObservation],
        source_path: str,
        objective: str,
    ) -> None:
        if self._registry.get("related_code") is None:
            return
        related_arguments: dict[str, object] = {
            "path": source_path,
            "query": objective[:200],
            "max_results": 2,
        }
        related_result = self._executor.execute(
            ToolCall(tool_name="related_code", arguments=related_arguments)
        )
        observations.append(
            AgentObservation(
                step=len(observations) + 1,
                tool_name="related_code",
                arguments=related_arguments,
                result=related_result,
            )
        )
        for path in self._result_paths(related_result)[:2]:
            read_arguments: dict[str, object] = {"path": path}
            observations.append(
                AgentObservation(
                    step=len(observations) + 1,
                    tool_name="read_file",
                    arguments=read_arguments,
                    result=self._executor.execute(
                        ToolCall(tool_name="read_file", arguments=read_arguments)
                    ),
                )
            )

    @staticmethod
    def _query(objective: str) -> str:
        path_match = re.search(
            r"\b[A-Za-z0-9_./\\-]+\.(?:py|js|ts|java|cs|dart|go|rs)\b",
            objective,
            re.IGNORECASE,
        )
        if path_match is not None:
            return path_match.group(0).replace("\\", "/")
        tokens = re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b", objective)
        code_tokens = [
            token
            for token in tokens
            if "_" in token or any(character.isupper() for character in token[1:])
        ]
        if code_tokens:
            return code_tokens[0]
        ignored = {"hangi", "nerede", "nasıl", "nedir", "içinde", "sınıfı", "dosyada"}
        named_tokens = [
            token
            for token in tokens
            if token[:1].isupper() and token.casefold() not in ignored
        ]
        if named_tokens:
            return max(named_tokens, key=len)
        words = [token for token in tokens if token.casefold() not in ignored]
        words.sort(key=len, reverse=True)
        return " ".join(words[:2])

    @staticmethod
    def _test_paths(objective: str) -> tuple[str, ...]:
        matches = re.findall(
            r"\b[A-Za-z0-9_./\\-]+\.py\b",
            objective,
            re.IGNORECASE,
        )
        return tuple(
            dict.fromkeys(
                path.replace("\\", "/")
                for path in matches
                if Path(path.replace("\\", "/")).name.casefold().startswith("test_")
                or Path(path.replace("\\", "/")).name.casefold().endswith("_test.py")
                or "tests" in {
                    part.casefold()
                    for part in Path(path.replace("\\", "/")).parts[:-1]
                }
            )
        )[:8]

    @staticmethod
    def _first_path(result: ToolResult) -> str | None:
        if not result.success:
            return None
        paths = result.metadata.get("paths")
        if not isinstance(paths, (list, tuple)):
            return None
        return next((path for path in paths if isinstance(path, str) and path), None)

    @staticmethod
    def _result_paths(result: ToolResult) -> list[str]:
        if not result.success:
            return []
        paths = result.metadata.get("paths")
        if not isinstance(paths, (list, tuple)):
            return []
        return [path for path in paths if isinstance(path, str) and path]
