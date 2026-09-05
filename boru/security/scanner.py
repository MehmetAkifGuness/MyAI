import ast
import re
from pathlib import Path

from boru.security.models import (
    SecurityFinding,
    SecurityScanReport,
    SecuritySeverity,
)
from boru.tools.workspace import WorkspaceAccessError, WorkspacePathResolver


class PythonSecurityScanner:
    """Sınırlı ve deterministik Python AST güvenlik kontrolleri uygular."""

    _SECRET_NAME = re.compile(
        r"(?:password|passwd|secret|api_?key|access_?token|private_?key)",
        re.IGNORECASE,
    )
    _PLACEHOLDER_SECRET = re.compile(
        r"^(?:|none|null|changeme|example|dummy|test|your[_ -].+|<.+>|\$\{.+\})$",
        re.IGNORECASE,
    )

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        max_paths: int = 8,
        max_file_bytes: int = 128 * 1024,
    ) -> None:
        if max_paths < 1 or max_file_bytes < 1:
            raise ValueError("Security Agent tarama sınırları pozitif olmalıdır.")
        self._resolver = WorkspacePathResolver(workspace_root)
        self._max_paths = max_paths
        self._max_file_bytes = max_file_bytes

    def scan(self, paths: tuple[str, ...]) -> SecurityScanReport:
        if not paths:
            raise ValueError("En az bir kaynak dosya belirtilmelidir.")
        if len(paths) > self._max_paths:
            raise ValueError(f"En fazla {self._max_paths} dosya taranabilir.")

        scanned: list[str] = []
        skipped: list[str] = []
        findings: list[SecurityFinding] = []
        for requested_path in paths:
            target = self._resolver.resolve(requested_path)
            if not target.is_file():
                raise WorkspaceAccessError(f"Tarama hedefi dosya değil: {requested_path}")
            relative = target.relative_to(self._resolver.root).as_posix()
            if target.suffix.casefold() != ".py":
                skipped.append(relative)
                continue
            source = self._read(target)
            try:
                tree = ast.parse(source, filename=relative)
            except SyntaxError as error:
                findings.append(
                    SecurityFinding(
                        relative,
                        error.lineno or 1,
                        "PY-SYNTAX",
                        SecuritySeverity.MEDIUM,
                        "Dosya AST güvenlik taraması için ayrıştırılamadı.",
                        "Önce Python söz dizimi hatasını düzeltin.",
                    )
                )
                scanned.append(relative)
                continue
            visitor = _PythonSecurityVisitor(relative)
            visitor.visit(tree)
            findings.extend(visitor.findings)
            scanned.append(relative)

        findings.sort(
            key=lambda finding: (
                -int(finding.severity),
                finding.path.casefold(),
                finding.line,
                finding.rule,
            )
        )
        return SecurityScanReport(tuple(scanned), tuple(findings), tuple(skipped))

    def _read(self, path: Path) -> str:
        if path.stat().st_size > self._max_file_bytes:
            raise WorkspaceAccessError("Dosya güvenlik tarama boyutu sınırını aşıyor.")
        try:
            return path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as error:
            raise WorkspaceAccessError("Dosya UTF-8 Python kaynağı değil.") from error


class _PythonSecurityVisitor(ast.NodeVisitor):
    _SUBPROCESS_CALLS = {
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "subprocess.Popen",
        "subprocess.run",
    }
    _DESERIALIZATION_CALLS = {
        "pickle.load",
        "pickle.loads",
        "dill.load",
        "dill.loads",
        "marshal.load",
        "marshal.loads",
    }
    _PATH_CALLS = {"open", "builtins.open", "io.open", "os.open", "pathlib.Path"}
    _REQUESTS_CALLS = {
        "requests.get",
        "requests.post",
        "requests.put",
        "requests.delete",
        "requests.request",
    }

    def __init__(self, path: str) -> None:
        self._path = path
        self._aliases: dict[str, str] = {}
        self._dynamic_strings: set[str] = set()
        self.findings: list[SecurityFinding] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local_name = alias.asname or alias.name.split(".", 1)[0]
            self._aliases[local_name] = alias.name

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module is None:
            return
        for alias in node.names:
            if alias.name == "*":
                continue
            self._aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"

    def visit_Call(self, node: ast.Call) -> None:
        call_name = self._call_name(node.func)
        if call_name in {"eval", "exec", "builtins.eval", "builtins.exec"}:
            self._add(
                node,
                "PY-EVAL-EXEC",
                SecuritySeverity.CRITICAL,
                f"{call_name} dinamik kod çalıştırabilir.",
                "Girdiyi veri olarak ayrıştırın ve izinli işlemleri açıkça eşleyin.",
            )
        if call_name in {"os.system", "os.popen"}:
            self._add(
                node,
                "PY-COMMAND-INJECTION",
                SecuritySeverity.CRITICAL,
                f"{call_name} shell komut enjeksiyonuna açıktır.",
                "Shell kullanmadan sabit executable ve argüman listesi çalıştırın.",
            )
        if (
            call_name in self._PATH_CALLS
            and node.args
            and self._literal_traversal(node.args[0])
        ):
            self._add(
                node,
                "PY-PATH-TRAVERSAL",
                SecuritySeverity.HIGH,
                "Dosya yolu üst dizine çıkan '..' bileşeni içeriyor.",
                "Yolu güvenilir bir köke çözümleyip kök sınırını doğrulayın.",
            )
        if call_name.endswith(".extractall"):
            self._add(
                node,
                "PY-ARCHIVE-TRAVERSAL",
                SecuritySeverity.MEDIUM,
                "Arşiv üyeleri doğrulanmadan topluca çıkarılıyor olabilir.",
                "Her üyenin hedef kök içinde kaldığını doğruladıktan sonra çıkarın.",
            )
        if call_name in self._SUBPROCESS_CALLS and self._keyword_true(node, "shell"):
            self._add(
                node,
                "PY-SUBPROCESS-SHELL",
                SecuritySeverity.CRITICAL,
                "subprocess çağrısında shell=True kullanılıyor.",
                "shell=False kullanın ve argümanları liste olarak geçin.",
            )
        if call_name in self._DESERIALIZATION_CALLS:
            self._add(
                node,
                "PY-INSECURE-DESERIALIZATION",
                SecuritySeverity.HIGH,
                f"{call_name} güvenilmeyen veride kod çalıştırabilir.",
                "JSON gibi veri odaklı bir biçim ve şema doğrulaması kullanın.",
            )
        if call_name == "yaml.load" and not self._has_safe_yaml_loader(node):
            self._add(
                node,
                "PY-UNSAFE-YAML",
                SecuritySeverity.HIGH,
                "yaml.load güvenli Loader olmadan kullanılıyor.",
                "yaml.safe_load veya yaml.SafeLoader kullanın.",
            )
        if call_name.endswith(".execute") and node.args and self._is_dynamic_string(node.args[0]):
            self._add(
                node,
                "PY-SQL-INJECTION",
                SecuritySeverity.HIGH,
                "Dinamik oluşturulan SQL sorgusu execute çağrısına veriliyor.",
                "Parametreli sorgu ve sürücünün placeholder mekanizmasını kullanın.",
            )
        if call_name in self._REQUESTS_CALLS and self._keyword_false(node, "verify"):
            self._add(
                node,
                "PY-TLS-VERIFY-DISABLED",
                SecuritySeverity.HIGH,
                "HTTP isteğinde TLS sertifika doğrulaması kapatılmış.",
                "verify=False seçeneğini kaldırın veya güvenilir CA yapılandırın.",
            )
        if call_name == "os.chmod" and len(node.args) > 1 and self._unsafe_mode(node.args[1]):
            self._add(
                node,
                "PY-WORLD-WRITABLE",
                SecuritySeverity.HIGH,
                "Dosya izni herkes için yazılabilir olarak ayarlanıyor.",
                "En az ayrıcalıkla 0o600 veya ihtiyaca uygun dar izin kullanın.",
            )
        if call_name == "tempfile.mktemp":
            self._add(
                node,
                "PY-INSECURE-TEMPFILE",
                SecuritySeverity.MEDIUM,
                "tempfile.mktemp yarış koşuluna açıktır.",
                "NamedTemporaryFile veya mkstemp kullanın.",
            )
        is_output_call = call_name == "print" or call_name.rsplit(".", 1)[-1] in {
            "debug",
            "info",
            "warning",
            "error",
            "critical",
        }
        if is_output_call and any(
            self._contains_secret_name(argument) for argument in node.args
        ):
            self._add(
                node,
                "PY-SECRET-LEAKAGE",
                SecuritySeverity.HIGH,
                "Hassas isimli değer log veya standart çıktıya yazılıyor.",
                "Sırrı kaldırın ya da güvenli biçimde maskeleyin.",
            )
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        names = [name for target in node.targets for name in self._assigned_names(target)]
        if self._is_dynamic_string(node.value):
            self._dynamic_strings.update(names)
        else:
            self._dynamic_strings.difference_update(names)
        self._check_hardcoded_secret(node, names, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            names = self._assigned_names(node.target)
            if self._is_dynamic_string(node.value):
                self._dynamic_strings.update(names)
            else:
                self._dynamic_strings.difference_update(names)
            self._check_hardcoded_secret(
                node,
                names,
                node.value,
            )
        self.generic_visit(node)

    def _check_hardcoded_secret(
        self,
        node: ast.AST,
        names: list[str],
        value: ast.expr,
    ) -> None:
        if not any(PythonSecurityScanner._SECRET_NAME.search(name) for name in names):
            return
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            return
        secret = value.value.strip()
        if len(secret) < 8 or PythonSecurityScanner._PLACEHOLDER_SECRET.fullmatch(secret):
            return
        self._add(
            node,
            "PY-HARDCODED-SECRET",
            SecuritySeverity.HIGH,
            "Hassas isimli değişkene sabit bir değer atanmış.",
            "Değeri ortam değişkeni veya ayrı bir secret manager üzerinden alın.",
        )

    def _add(
        self,
        node: ast.AST,
        rule: str,
        severity: SecuritySeverity,
        message: str,
        recommendation: str,
    ) -> None:
        self.findings.append(
            SecurityFinding(
                self._path,
                getattr(node, "lineno", 1),
                rule,
                severity,
                message,
                recommendation,
            )
        )

    def _call_name(self, node: ast.expr) -> str:
        parts: list[str] = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        parts.reverse()
        if parts and parts[0] in self._aliases:
            parts[:1] = self._aliases[parts[0]].split(".")
        return ".".join(parts)

    @staticmethod
    def _keyword_true(node: ast.Call, name: str) -> bool:
        return any(
            keyword.arg == name
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
            for keyword in node.keywords
        )

    @staticmethod
    def _keyword_false(node: ast.Call, name: str) -> bool:
        return any(
            keyword.arg == name
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is False
            for keyword in node.keywords
        )

    def _has_safe_yaml_loader(self, node: ast.Call) -> bool:
        return any(
            keyword.arg == "Loader"
            and self._call_name(keyword.value) in {
                "SafeLoader",
                "yaml.SafeLoader",
                "CSafeLoader",
                "yaml.CSafeLoader",
            }
            for keyword in node.keywords
        )

    def _is_dynamic_string(self, node: ast.expr) -> bool:
        return isinstance(node, (ast.JoinedStr, ast.BinOp)) or (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "format"
        ) or (isinstance(node, ast.Name) and node.id in self._dynamic_strings)

    @staticmethod
    def _unsafe_mode(node: ast.expr) -> bool:
        return (
            isinstance(node, ast.Constant)
            and isinstance(node.value, int)
            and bool(node.value & 0o002)
        )

    @staticmethod
    def _literal_traversal(node: ast.expr) -> bool:
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            return False
        return ".." in node.value.replace("\\", "/").split("/")

    @staticmethod
    def _assigned_names(node: ast.expr) -> list[str]:
        if isinstance(node, ast.Name):
            return [node.id]
        if isinstance(node, ast.Attribute):
            return [node.attr]
        if isinstance(node, (ast.Tuple, ast.List)):
            return [
                name
                for item in node.elts
                for name in _PythonSecurityVisitor._assigned_names(item)
            ]
        return []

    @staticmethod
    def _contains_secret_name(node: ast.AST) -> bool:
        return any(
            (
                isinstance(child, ast.Name)
                and PythonSecurityScanner._SECRET_NAME.search(child.id)
            )
            or (
                isinstance(child, ast.Attribute)
                and PythonSecurityScanner._SECRET_NAME.search(child.attr)
            )
            for child in ast.walk(node)
        )
