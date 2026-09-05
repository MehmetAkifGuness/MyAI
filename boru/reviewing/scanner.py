import ast
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from boru.reviewing.models import CodeReviewReport, ReviewFinding, ReviewSeverity
from boru.tools.workspace import WorkspaceAccessError, WorkspacePathResolver


@dataclass(frozen=True, slots=True)
class _FunctionRecord:
    path: str
    line: int
    name: str
    fingerprint: str


class PythonCodeReviewScanner:
    """Seçili Python dosyalarında deterministik bakım ve doğruluk kontrolleri yapar."""

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        max_paths: int = 8,
        max_file_bytes: int = 128 * 1024,
        max_function_lines: int = 80,
        max_complexity: int = 12,
        max_nesting: int = 4,
        max_parameters: int = 7,
        max_class_lines: int = 300,
        max_class_methods: int = 20,
    ) -> None:
        limits = (
            max_paths,
            max_file_bytes,
            max_function_lines,
            max_complexity,
            max_nesting,
            max_parameters,
            max_class_lines,
            max_class_methods,
        )
        if min(limits) < 1:
            raise ValueError("Code Review Agent sınırları pozitif olmalıdır.")
        self._resolver = WorkspacePathResolver(workspace_root)
        self._max_paths = max_paths
        self._max_file_bytes = max_file_bytes
        self._limits = limits[2:]

    def scan(self, paths: tuple[str, ...]) -> CodeReviewReport:
        if not paths:
            raise ValueError("En az bir kaynak dosya belirtilmelidir.")
        if len(paths) > self._max_paths:
            raise ValueError(f"En fazla {self._max_paths} dosya incelenebilir.")

        reviewed: list[str] = []
        skipped: list[str] = []
        findings: list[ReviewFinding] = []
        functions: list[_FunctionRecord] = []
        for requested_path in paths:
            target = self._resolver.resolve(requested_path)
            if not target.is_file():
                raise WorkspaceAccessError(f"İnceleme hedefi dosya değil: {requested_path}")
            relative = target.relative_to(self._resolver.root).as_posix()
            if target.suffix.casefold() != ".py":
                skipped.append(relative)
                continue
            source = self._read(target)
            try:
                tree = ast.parse(source, filename=relative)
            except SyntaxError as error:
                findings.append(
                    ReviewFinding(
                        relative,
                        error.lineno or 1,
                        "REVIEW-SYNTAX",
                        ReviewSeverity.ERROR,
                        "Dosya Python AST olarak ayrıştırılamadı.",
                        "Önce söz dizimi hatasını düzeltin.",
                    )
                )
                reviewed.append(relative)
                continue
            visitor = _ReviewVisitor(relative, self._limits)
            visitor.visit(tree)
            findings.extend(visitor.findings)
            functions.extend(visitor.functions)
            reviewed.append(relative)

        findings.extend(self._duplicate_findings(functions))
        findings.sort(
            key=lambda finding: (
                -int(finding.severity),
                finding.path.casefold(),
                finding.line,
                finding.rule,
            )
        )
        return CodeReviewReport(tuple(reviewed), tuple(findings), tuple(skipped))

    def _read(self, path: Path) -> str:
        if path.stat().st_size > self._max_file_bytes:
            raise WorkspaceAccessError("Dosya code review boyut sınırını aşıyor.")
        try:
            return path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as error:
            raise WorkspaceAccessError("Dosya UTF-8 Python kaynağı değil.") from error

    @staticmethod
    def _duplicate_findings(
        records: list[_FunctionRecord],
    ) -> list[ReviewFinding]:
        groups: dict[str, list[_FunctionRecord]] = defaultdict(list)
        for record in records:
            groups[record.fingerprint].append(record)

        findings: list[ReviewFinding] = []
        for duplicates in groups.values():
            locations = {(item.path, item.line) for item in duplicates}
            if len(locations) < 2:
                continue
            first = duplicates[0]
            references = ", ".join(
                f"{item.path}:{item.line} ({item.name})"
                for item in duplicates[1:4]
            )
            findings.append(
                ReviewFinding(
                    first.path,
                    first.line,
                    "REVIEW-DUPLICATE-CODE",
                    ReviewSeverity.WARNING,
                    f"{first.name} gövdesi başka fonksiyonlarla aynı: {references}.",
                    "Ortak davranışı tek ve anlamlı bir yardımcıda birleştirin.",
                )
            )
        return findings


class _ReviewVisitor(ast.NodeVisitor):
    _CLASS_NAME = re.compile(r"^_?[A-Z][A-Za-z0-9]*$")
    _FUNCTION_NAME = re.compile(r"^_*[a-z][a-z0-9_]*$")
    _MUTABLE_DEFAULTS = (ast.List, ast.Dict, ast.Set)
    _BRANCH_NODES = (
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.Try,
        ast.IfExp,
        ast.Match,
        ast.comprehension,
    )

    def __init__(self, path: str, limits: tuple[int, ...]) -> None:
        self._path = path
        (
            self._max_function_lines,
            self._max_complexity,
            self._max_nesting,
            self._max_parameters,
            self._max_class_lines,
            self._max_class_methods,
        ) = limits
        self.findings: list[ReviewFinding] = []
        self.functions: list[_FunctionRecord] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if self._CLASS_NAME.fullmatch(node.name) is None:
            self._add(
                node,
                "REVIEW-CLASS-NAMING",
                ReviewSeverity.WARNING,
                f"Sınıf adı '{node.name}' PascalCase biçiminde değil.",
                "Sınıfı PascalCase biçiminde adlandırın.",
            )
        line_count = self._line_count(node)
        method_count = sum(
            isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            for item in node.body
        )
        if line_count > self._max_class_lines or method_count > self._max_class_methods:
            self._add(
                node,
                "REVIEW-LARGE-CLASS",
                ReviewSeverity.WARNING,
                f"Sınıf {line_count} satır ve {method_count} metot içeriyor.",
                "Birlikte değişmeyen sorumlulukları ayrı bileşenlere ayırmayı değerlendirin.",
            )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._review_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._review_function(node)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is None or (
            isinstance(node.type, ast.Name) and node.type.id in {"Exception", "BaseException"}
        ):
            self._add(
                node,
                "REVIEW-BROAD-EXCEPT",
                ReviewSeverity.WARNING,
                "Çok geniş bir exception yakalanıyor.",
                "Beklenen dar exception türlerini ayrı ayrı yakalayın.",
            )
        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            self._add(
                node,
                "REVIEW-SILENT-EXCEPT",
                ReviewSeverity.ERROR,
                "Exception hiçbir işlem yapılmadan yutuluyor.",
                "Hatayı ele alın, bağlamıyla kaydedin veya yeniden yükseltin.",
            )
        self.generic_visit(node)

    def _review_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if not self._is_valid_function_name(node.name):
            self._add(
                node,
                "REVIEW-FUNCTION-NAMING",
                ReviewSeverity.WARNING,
                f"Fonksiyon adı '{node.name}' snake_case biçiminde değil.",
                "Fonksiyonu snake_case biçiminde adlandırın.",
            )

        line_count = self._line_count(node)
        if line_count > self._max_function_lines:
            self._add(
                node,
                "REVIEW-LONG-FUNCTION",
                ReviewSeverity.WARNING,
                f"Fonksiyon {line_count} satırla bakım sınırını aşıyor.",
                "Bağımsız sorumlulukları küçük yardımcı fonksiyonlara ayırın.",
            )

        complexity = self._complexity(node)
        if complexity > self._max_complexity:
            self._add(
                node,
                "REVIEW-COMPLEX-FUNCTION",
                ReviewSeverity.WARNING,
                f"Fonksiyonun yaklaşık çevrimsel karmaşıklığı {complexity}.",
                "Koşul dallarını sadeleştirin ve bağımsız kararları ayırın.",
            )

        nesting = self._max_statement_nesting(node.body)
        if nesting > self._max_nesting:
            self._add(
                node,
                "REVIEW-DEEP-NESTING",
                ReviewSeverity.WARNING,
                f"Fonksiyonun kontrol akışı {nesting} seviye iç içe.",
                "Erken dönüşler veya yardımcı fonksiyonlarla iç içeliği azaltın.",
            )

        parameter_count = (
            len(node.args.posonlyargs)
            + len(node.args.args)
            + len(node.args.kwonlyargs)
        )
        if node.args.vararg is not None:
            parameter_count += 1
        if node.args.kwarg is not None:
            parameter_count += 1
        if node.args.args and node.args.args[0].arg in {"self", "cls"}:
            parameter_count -= 1
        if parameter_count > self._max_parameters:
            self._add(
                node,
                "REVIEW-MANY-PARAMETERS",
                ReviewSeverity.WARNING,
                f"Fonksiyon {parameter_count} bağımsız parametre alıyor.",
                "İlişkili girdileri anlamlı bir veri nesnesinde toplamayı değerlendirin.",
            )

        defaults = (*node.args.defaults, *(item for item in node.args.kw_defaults if item))
        if any(self._is_mutable_default(default) for default in defaults):
            self._add(
                node,
                "REVIEW-MUTABLE-DEFAULT",
                ReviewSeverity.ERROR,
                "Fonksiyon değiştirilebilir varsayılan parametre kullanıyor.",
                "None kullanıp değeri fonksiyon içinde oluşturun.",
            )

        unreachable = self._first_unreachable(node.body)
        if unreachable is not None:
            self._add(
                unreachable,
                "REVIEW-UNREACHABLE-CODE",
                ReviewSeverity.WARNING,
                "Kesin dönüş/yükseltme sonrasında ulaşılamayan kod var.",
                "Ulaşılamayan ifadeyi kaldırın veya kontrol akışını düzeltin.",
            )

        if len(node.body) >= 3 and node.name not in {"__init__", "__repr__"}:
            fingerprint = ast.dump(ast.Module(body=node.body, type_ignores=[]))
            self.functions.append(
                _FunctionRecord(self._path, node.lineno, node.name, fingerprint)
            )

    @classmethod
    def _is_mutable_default(cls, node: ast.expr) -> bool:
        if isinstance(node, cls._MUTABLE_DEFAULTS):
            return True
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"dict", "list", "set"}
        )

    @classmethod
    def _complexity(cls, node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
        complexity = 1
        for child in cls._walk_function_body(node.body):
            if isinstance(child, cls._BRANCH_NODES):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += max(len(child.values) - 1, 0)
            elif isinstance(child, ast.ExceptHandler):
                complexity += 1
        return complexity

    @classmethod
    def _walk_function_body(cls, body: list[ast.stmt]):
        for statement in body:
            yield statement
            for child in ast.iter_child_nodes(statement):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    continue
                yield from cls._walk_nodes(child)

    @classmethod
    def _walk_nodes(cls, node: ast.AST):
        yield node
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            yield from cls._walk_nodes(child)

    @classmethod
    def _max_statement_nesting(cls, body: list[ast.stmt], level: int = 0) -> int:
        maximum = level
        for statement in body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            child_level = level + 1 if isinstance(statement, cls._BRANCH_NODES) else level
            maximum = max(maximum, child_level)
            for _, value in ast.iter_fields(statement):
                if isinstance(value, list) and value and all(
                    isinstance(item, ast.stmt) for item in value
                ):
                    maximum = max(
                        maximum,
                        cls._max_statement_nesting(value, child_level),
                    )
        return maximum

    @classmethod
    def _first_unreachable(cls, body: list[ast.stmt]) -> ast.stmt | None:
        terminated = False
        for statement in body:
            if terminated:
                return statement
            for _, value in ast.iter_fields(statement):
                if isinstance(value, list) and value and all(
                    isinstance(item, ast.stmt) for item in value
                ):
                    nested = cls._first_unreachable(value)
                    if nested is not None:
                        return nested
            terminated = isinstance(statement, (ast.Return, ast.Raise, ast.Break, ast.Continue))
        return None

    @classmethod
    def _is_valid_function_name(cls, name: str) -> bool:
        return (
            name.startswith("__") and name.endswith("__")
        ) or cls._FUNCTION_NAME.fullmatch(name) is not None

    @staticmethod
    def _line_count(node: ast.AST) -> int:
        return max((getattr(node, "end_lineno", node.lineno) or node.lineno) - node.lineno + 1, 1)

    def _add(
        self,
        node: ast.AST,
        rule: str,
        severity: ReviewSeverity,
        message: str,
        recommendation: str,
    ) -> None:
        self.findings.append(
            ReviewFinding(
                self._path,
                getattr(node, "lineno", 1),
                rule,
                severity,
                message,
                recommendation,
            )
        )
