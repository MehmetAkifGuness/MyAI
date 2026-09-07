import re

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
        return observations

    @staticmethod
    def _query(objective: str) -> str:
        tokens = re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b", objective)
        code_tokens = [
            token
            for token in tokens
            if "_" in token or any(character.isupper() for character in token[1:])
        ]
        if code_tokens:
            return code_tokens[0]
        ignored = {"hangi", "nerede", "nasıl", "nedir", "içinde", "sınıfı", "dosyada"}
        words = [token for token in tokens if token.casefold() not in ignored]
        words.sort(key=len, reverse=True)
        return " ".join(words[:2])

    @staticmethod
    def _first_path(result: ToolResult) -> str | None:
        if not result.success:
            return None
        paths = result.metadata.get("paths")
        if not isinstance(paths, (list, tuple)):
            return None
        return next((path for path in paths if isinstance(path, str) and path), None)

