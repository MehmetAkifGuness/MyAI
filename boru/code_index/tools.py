from boru.code_index.index import SafeCodeIndex
from boru.code_index.impact import SafeCodeImpactIndex
from boru.code_index.relationships import SafeCodeRelationshipIndex
from boru.tools.arguments import ToolArgumentSchema, ToolArgumentSpec, ToolArgumentType
from boru.tools.models import ToolResult, ToolRisk


class ProjectOverviewTool:
    def __init__(self, index: SafeCodeIndex) -> None:
        self._index = index

    @property
    def name(self) -> str:
        return "project_overview"

    @property
    def description(self) -> str:
        return "Güvenli proje indeksinin dosya, sembol ve uzantı özetini verir. Argüman almaz."

    @property
    def risk(self) -> ToolRisk:
        return ToolRisk.READ_ONLY

    @property
    def argument_schema(self) -> ToolArgumentSchema:
        return ToolArgumentSchema()

    def execute(self, arguments: dict[str, object]) -> ToolResult:
        if arguments:
            raise ValueError("project_overview argüman kabul etmez.")
        summary = self._index.summary()
        suffixes = ", ".join(f"{suffix}: {count}" for suffix, count in summary.suffix_counts)
        return ToolResult(
            tool_name=self.name,
            success=True,
            content=(
                "PROJE İNDEKSİ\n"
                f"Dosya: {summary.file_count}\n"
                f"Python sembolü: {summary.symbol_count}\n"
                f"Uzantılar: {suffixes or '(yok)'}"
            ),
            metadata={"file_count": summary.file_count, "symbol_count": summary.symbol_count},
        )


class CodeSearchTool:
    def __init__(self, index: SafeCodeIndex) -> None:
        self._index = index

    @property
    def name(self) -> str:
        return "search_code"

    @property
    def description(self) -> str:
        return "Proje yolları, Python sembolleri ve metin satırlarında terim arar. Argümanlar: query, max_results."

    @property
    def risk(self) -> ToolRisk:
        return ToolRisk.READ_ONLY

    @property
    def argument_schema(self) -> ToolArgumentSchema:
        return ToolArgumentSchema(
            arguments=(
                ToolArgumentSpec("query", ToolArgumentType.STRING, strip=True, allow_empty=False, max_length=200),
                ToolArgumentSpec(
                    "max_results",
                    ToolArgumentType.INTEGER,
                    required=False,
                    has_default=True,
                    default=12,
                ),
            )
        )

    def execute(self, arguments: dict[str, object]) -> ToolResult:
        query = arguments["query"]
        max_results = arguments["max_results"]
        if not isinstance(query, str) or isinstance(max_results, bool) or not isinstance(max_results, int):
            raise ValueError("search_code argümanları geçersiz.")
        hits = self._index.search(query, max_results=max_results)
        lines = [f"KOD ARAMA\nSorgu: {query}\nSonuç: {len(hits)}"]
        lines.extend(
            f"- {hit.path}:{hit.line} | {hit.preview}"
            for hit in hits
        )
        if not hits:
            lines.append("(eşleşme yok)")
        return ToolResult(
            tool_name=self.name,
            success=True,
            content="\n".join(lines),
            metadata={
                "query": query,
                "result_count": len(hits),
                "paths": tuple(dict.fromkeys(hit.path for hit in hits)),
            },
        )


class FileSymbolsTool:
    def __init__(self, index: SafeCodeIndex) -> None:
        self._index = index

    @property
    def name(self) -> str:
        return "file_symbols"

    @property
    def description(self) -> str:
        return "Bir Python dosyasındaki sınıf, fonksiyon ve modül değişkenlerini listeler. Argüman: path."

    @property
    def risk(self) -> ToolRisk:
        return ToolRisk.READ_ONLY

    @property
    def argument_schema(self) -> ToolArgumentSchema:
        return ToolArgumentSchema(
            arguments=(
                ToolArgumentSpec("path", ToolArgumentType.STRING, strip=True, allow_empty=False, max_length=1024),
            )
        )

    def execute(self, arguments: dict[str, object]) -> ToolResult:
        path = arguments["path"]
        if not isinstance(path, str):
            raise ValueError("file_symbols path argümanı metin olmalıdır.")
        symbols = self._index.symbols(path)
        lines = [f"DOSYA SEMBOLLERİ\nDosya: {path}\nSembol: {len(symbols)}"]
        lines.extend(
            f"- {symbol.kind.value} {symbol.qualified_name} ({symbol.line}-{symbol.end_line})"
            for symbol in symbols
        )
        if not symbols:
            lines.append("(Python sembolü yok)")
        return ToolResult(
            tool_name=self.name,
            success=True,
            content="\n".join(lines),
            metadata={"path": path, "symbol_count": len(symbols)},
        )


class RelatedCodeTool:
    def __init__(self, index: SafeCodeRelationshipIndex) -> None:
        self._index = index

    @property
    def name(self) -> str:
        return "related_code"

    @property
    def description(self) -> str:
        return "Python dosyasının proje içi importlarını çağrı ve sorgu ilgisine göre sıralar. Argümanlar: path, query, max_results."

    @property
    def risk(self) -> ToolRisk:
        return ToolRisk.READ_ONLY

    @property
    def argument_schema(self) -> ToolArgumentSchema:
        return ToolArgumentSchema(
            arguments=(
                ToolArgumentSpec("path", ToolArgumentType.STRING, strip=True, allow_empty=False, max_length=1024),
                ToolArgumentSpec(
                    "query",
                    ToolArgumentType.STRING,
                    required=False,
                    strip=True,
                    max_length=200,
                    has_default=True,
                    default="",
                ),
                ToolArgumentSpec(
                    "max_results",
                    ToolArgumentType.INTEGER,
                    required=False,
                    has_default=True,
                    default=3,
                ),
            )
        )

    def execute(self, arguments: dict[str, object]) -> ToolResult:
        path = arguments["path"]
        query = arguments["query"]
        max_results = arguments["max_results"]
        if not isinstance(path, str) or not isinstance(query, str):
            raise ValueError("related_code path ve query argümanları metin olmalıdır.")
        if isinstance(max_results, bool) or not isinstance(max_results, int):
            raise ValueError("related_code max_results argümanı tam sayı olmalıdır.")
        related = self._index.related_files(path, query, max_results=max_results)
        lines = [f"İLİŞKİLİ KOD\nKaynak: {path}\nSonuç: {len(related)}"]
        for item in related:
            calls = ", ".join(item.matched_calls) or "doğrudan çağrı eşleşmesi yok"
            lines.append(
                f"- {item.path} | import: {item.imported_via} | çağrı eşleşmesi: {calls}"
            )
        if not related:
            lines.append("(proje içi Python bağımlılığı yok)")
        return ToolResult(
            tool_name=self.name,
            success=True,
            content="\n".join(lines),
            metadata={
                "path": path,
                "result_count": len(related),
                "paths": tuple(item.path for item in related),
            },
        )


class ImpactAnalysisTool:
    def __init__(self, index: SafeCodeImpactIndex) -> None:
        self._index = index

    @property
    def name(self) -> str:
        return "impact_analysis"

    @property
    def description(self) -> str:
        return (
            "Bir Python dosyasını doğrudan veya dolaylı import eden proje dosyalarını ve "
            "testleri bulur. Argümanlar: path, max_depth, max_results."
        )

    @property
    def risk(self) -> ToolRisk:
        return ToolRisk.READ_ONLY

    @property
    def argument_schema(self) -> ToolArgumentSchema:
        return ToolArgumentSchema(
            arguments=(
                ToolArgumentSpec(
                    "path",
                    ToolArgumentType.STRING,
                    strip=True,
                    allow_empty=False,
                    max_length=1024,
                ),
                ToolArgumentSpec(
                    "max_depth",
                    ToolArgumentType.INTEGER,
                    required=False,
                    has_default=True,
                    default=3,
                ),
                ToolArgumentSpec(
                    "max_results",
                    ToolArgumentType.INTEGER,
                    required=False,
                    has_default=True,
                    default=20,
                ),
            )
        )

    def execute(self, arguments: dict[str, object]) -> ToolResult:
        path = arguments["path"]
        max_depth = arguments["max_depth"]
        max_results = arguments["max_results"]
        if not isinstance(path, str):
            raise ValueError("impact_analysis path argümanı metin olmalıdır.")
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in (max_depth, max_results)
        ):
            raise ValueError("impact_analysis sınırları tam sayı olmalıdır.")
        impacted = self._index.impacted_files(
            path,
            max_depth=max_depth,
            max_results=max_results,
        )
        lines = [f"ETKİ ANALİZİ\nKaynak: {path}\nSonuç: {len(impacted)}"]
        lines.extend(
            f"- {item.path} | mesafe: {item.distance} | tür: "
            f"{'test' if item.is_test else 'çağıran'} | import: {item.imported_via}"
            for item in impacted
        )
        if not impacted:
            lines.append("(proje içi ters bağımlılık bulunamadı)")
        return ToolResult(
            tool_name=self.name,
            success=True,
            content="\n".join(lines),
            metadata={
                "path": path,
                "result_count": len(impacted),
                "paths": tuple(item.path for item in impacted),
                "test_paths": tuple(item.path for item in impacted if item.is_test),
                "impacts": tuple(
                    {
                        "path": item.path,
                        "distance": item.distance,
                        "imported_via": item.imported_via,
                        "is_test": item.is_test,
                    }
                    for item in impacted
                ),
                "absence_is_evidence": True,
            },
        )
