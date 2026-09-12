"""
boru.code_index.graph
=====================
Proje genelinde iki yönlü bağımlılık grafiği (Dependency Graph), sembol arama
ve çoklu dosya refactor planlama motoru.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import difflib
import os
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True, slots=True)
class FileDependencyReport:
    target_path: str
    forward_imports: tuple[str, ...]
    reverse_dependents: tuple[str, ...]
    associated_tests: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClassHierarchyReport:
    """Sınıfın kalıtım hiyerarşisi, alt/üst sınıfları, metotları ve decorator'ları."""
    class_name: str
    definition_path: str | None
    line_number: int | None
    base_classes: tuple[str, ...]
    subclasses: tuple[str, ...]
    methods: tuple[str, ...]
    decorators: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TypeUsageLocation:
    """Tip anotasyonu (parametre, dönüş veya değişken tipi) kullanım konumu."""
    path: str
    line_number: int
    kind: str  # 'param_type', 'return_type', 'variable_type'
    symbol_name: str
    enclosing_symbol: str
    snippet: str


@dataclass(frozen=True, slots=True)
class SymbolLocation:
    path: str
    line_number: int
    kind: str  # 'definition', 'import', 'call_or_attr'
    snippet: str


@dataclass(frozen=True, slots=True)
class FileRenameChange:
    path: str
    old_content: str
    new_content: str
    diff: str
    occurrences: int


@dataclass(frozen=True, slots=True)
class SymbolRenamePlan:
    symbol_old: str
    symbol_new: str
    changes: tuple[FileRenameChange, ...]
    total_files: int
    total_replacements: int


class ProjectDependencyGraph:
    """
    Tüm projedeki Python dosyalarını tarayarak bağımlılık ilişkilerini
    ve sembol kullanımlarını haritalandırır.
    """

    def __init__(self, project_root: str | Path = ".") -> None:
        self._root = Path(project_root).resolve()

    def _list_python_files(self) -> list[Path]:
        py_files: list[Path] = []
        for root, dirs, files in os.walk(self._root):
            dirs[:] = [
                d for d in dirs
                if not d.startswith(".")
                and d not in {"__pycache__", "venv", ".venv", "env", "node_modules"}
            ]
            for file in files:
                if file.endswith(".py"):
                    py_files.append(Path(root) / file)
        return py_files

    def _module_to_relpath(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for file in self._list_python_files():
            rel = file.relative_to(self._root).as_posix()
            mod = rel[:-3].replace("/", ".")
            if mod.endswith(".__init__"):
                mod = mod[:-9]
            mapping[mod] = rel
        return mapping

    def analyze_file(self, target_path: str | Path) -> FileDependencyReport:
        norm_target = Path(target_path)
        if norm_target.is_absolute():
            rel_target = norm_target.relative_to(self._root).as_posix()
        else:
            rel_target = norm_target.as_posix()

        py_files = self._list_python_files()
        mod_map = self._module_to_relpath()
        rev_mod_map = {v: k for k, v in mod_map.items()}

        target_mod = rev_mod_map.get(rel_target, rel_target.replace("/", ".").replace(".py", ""))

        forward: set[str] = set()
        dependents: set[str] = set()
        tests: set[str] = set()

        # Hedef dosyanın kendi importları
        target_full = self._root / rel_target
        if target_full.exists():
            try:
                tree = ast.parse(target_full.read_text(encoding="utf-8", errors="replace"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name in mod_map:
                                forward.add(mod_map[alias.name])
                    elif isinstance(node, ast.ImportFrom):
                        if node.module and node.module in mod_map:
                            forward.add(mod_map[node.module])
            except Exception:
                pass

        # Diğer dosyaların hedefi import etmesi (Ters bağımlılık)
        for file in py_files:
            rel = file.relative_to(self._root).as_posix()
            if rel == rel_target:
                continue
            try:
                content = file.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    matched = False
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name == target_mod or alias.name.startswith(target_mod + "."):
                                matched = True
                    elif isinstance(node, ast.ImportFrom):
                        if node.module and (node.module == target_mod or node.module.startswith(target_mod + ".")):
                            matched = True
                    if matched:
                        if rel.startswith("tests/") or "test" in rel:
                            tests.add(rel)
                        else:
                            dependents.add(rel)
                        break
            except Exception:
                continue

        return FileDependencyReport(
            target_path=rel_target,
            forward_imports=tuple(sorted(forward)),
            reverse_dependents=tuple(sorted(dependents)),
            associated_tests=tuple(sorted(tests)),
        )

    def find_symbol_references(self, symbol_name: str) -> tuple[SymbolLocation, ...]:
        clean_symbol = symbol_name.strip()
        results: list[SymbolLocation] = []

        for file in self._list_python_files():
            rel = file.relative_to(self._root).as_posix()
            try:
                content = file.read_text(encoding="utf-8", errors="replace")
                if clean_symbol not in content:
                    continue
                lines = content.splitlines()
                tree = ast.parse(content)

                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        if node.name == clean_symbol:
                            snippet = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
                            results.append(
                                SymbolLocation(
                                    path=rel,
                                    line_number=node.lineno,
                                    kind="tanım",
                                    snippet=snippet,
                                )
                            )
                    elif isinstance(node, ast.ImportFrom):
                        for alias in node.names:
                            if alias.name == clean_symbol:
                                snippet = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
                                results.append(
                                    SymbolLocation(
                                        path=rel,
                                        line_number=node.lineno,
                                        kind="import",
                                        snippet=snippet,
                                    )
                                )
                    elif isinstance(node, ast.Name):
                        if node.id == clean_symbol and isinstance(node.ctx, ast.Load):
                            snippet = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
                            results.append(
                                SymbolLocation(
                                    path=rel,
                                    line_number=node.lineno,
                                    kind="kullanım",
                                    snippet=snippet,
                                )
                            )
                    elif isinstance(node, ast.Attribute):
                        if node.attr == clean_symbol and isinstance(node.ctx, ast.Load):
                            snippet = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
                            results.append(
                                SymbolLocation(
                                    path=rel,
                                    line_number=node.lineno,
                                    kind="kullanım",
                                    snippet=snippet,
                                )
                            )
            except Exception:
                continue

        results.sort(key=lambda x: (x.path, x.line_number))
        return tuple(results)

    def find_class_hierarchy(self, class_name: str) -> ClassHierarchyReport | None:
        """
        Belirtilen sınıfın (class_name) kalıtım hiyerarşisini, üst sınıflarını (bases),
        alt sınıflarını (subclasses), tanımlı metotlarını ve decorator'larını çıkarır.
        """
        clean_name = class_name.strip()
        py_files = self._list_python_files()

        class_definitions: dict[str, dict] = {}
        subclass_map: dict[str, list[str]] = {}

        for file in py_files:
            rel = file.relative_to(self._root).as_posix()
            try:
                content = file.read_text(encoding="utf-8", errors="replace")
                if "class " not in content:
                    continue
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if not isinstance(node, ast.ClassDef):
                        continue
                    bases: list[str] = []
                    for b in node.bases:
                        if isinstance(b, ast.Name):
                            bases.append(b.id)
                        elif isinstance(b, ast.Attribute):
                            bases.append(b.attr)
                    methods = [
                        m.name for m in node.body
                        if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                    ]
                    decorators: list[str] = []
                    for d in node.decorator_list:
                        if isinstance(d, ast.Name):
                            decorators.append(d.id)
                        elif isinstance(d, ast.Attribute):
                            decorators.append(d.attr)
                        elif isinstance(d, ast.Call):
                            if isinstance(d.func, ast.Name):
                                decorators.append(d.func.id)
                            elif isinstance(d.func, ast.Attribute):
                                decorators.append(d.func.attr)

                    class_definitions[node.name] = {
                        "path": rel,
                        "line": node.lineno,
                        "bases": tuple(bases),
                        "methods": tuple(methods),
                        "decorators": tuple(decorators),
                    }
                    for b in bases:
                        subclass_map.setdefault(b, []).append(node.name)
            except Exception:
                continue

        target_info = class_definitions.get(clean_name)
        direct_subclasses = subclass_map.get(clean_name, [])

        if target_info is None and not direct_subclasses:
            return None

        return ClassHierarchyReport(
            class_name=clean_name,
            definition_path=target_info["path"] if target_info else None,
            line_number=target_info["line"] if target_info else None,
            base_classes=target_info["bases"] if target_info else (),
            subclasses=tuple(sorted(set(direct_subclasses))),
            methods=target_info["methods"] if target_info else (),
            decorators=target_info["decorators"] if target_info else (),
        )

    def find_typed_usages(self, type_name: str) -> tuple[TypeUsageLocation, ...]:
        """
        Belirtilen tip adının (type_name) fonksiyon parametresi, dönüş tipi
        veya değişken tipi anotasyonlarında nerelerde kullanıldığını tespit eder.
        """
        clean_name = type_name.strip().casefold()
        results: list[TypeUsageLocation] = []

        for file in self._list_python_files():
            rel = file.relative_to(self._root).as_posix()
            try:
                content = file.read_text(encoding="utf-8", errors="replace")
                if clean_name not in content.casefold():
                    continue
                lines = content.splitlines()
                tree = ast.parse(content)

                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        all_args = list(node.args.args) + list(node.args.posonlyargs) + list(node.args.kwonlyargs)
                        for arg in all_args:
                            if arg.annotation:
                                names = self._extract_ast_names(arg.annotation)
                                if clean_name in names:
                                    line_no = getattr(arg, "lineno", node.lineno)
                                    snippet = lines[line_no - 1].strip() if line_no <= len(lines) else ""
                                    results.append(
                                        TypeUsageLocation(
                                            path=rel,
                                            line_number=line_no,
                                            kind="param_type",
                                            symbol_name=type_name.strip(),
                                            enclosing_symbol=node.name,
                                            snippet=snippet,
                                        )
                                    )
                        if node.returns:
                            names = self._extract_ast_names(node.returns)
                            if clean_name in names:
                                snippet = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
                                results.append(
                                    TypeUsageLocation(
                                        path=rel,
                                        line_number=node.lineno,
                                        kind="return_type",
                                        symbol_name=type_name.strip(),
                                        enclosing_symbol=node.name,
                                        snippet=snippet,
                                    )
                                )
                    elif isinstance(node, ast.AnnAssign):
                        if node.annotation:
                            names = self._extract_ast_names(node.annotation)
                            if clean_name in names:
                                snippet = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
                                results.append(
                                    TypeUsageLocation(
                                        path=rel,
                                        line_number=node.lineno,
                                        kind="variable_type",
                                        symbol_name=type_name.strip(),
                                        enclosing_symbol="",
                                        snippet=snippet,
                                    )
                                )
            except Exception:
                continue

        results.sort(key=lambda x: (x.path, x.line_number))
        return tuple(results)

    @staticmethod
    def _extract_ast_names(node: ast.AST | None) -> set[str]:
        names: set[str] = set()
        if node is None:
            return names
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                names.add(child.id.casefold())
            elif isinstance(child, ast.Attribute):
                names.add(child.attr.casefold())
        return names

    def plan_symbol_rename(
        self,
        target_path: str,
        old_symbol: str,
        new_symbol: str,
    ) -> SymbolRenamePlan:
        dep_report = self.analyze_file(target_path)
        relevant_files = [dep_report.target_path] + list(dep_report.reverse_dependents) + list(dep_report.associated_tests)

        changes: list[FileRenameChange] = []
        total_replacements = 0

        for rel_path in relevant_files:
            file_full = self._root / rel_path
            if not file_full.exists():
                continue
            original = file_full.read_text(encoding="utf-8", errors="replace")
            if old_symbol not in original:
                continue

            # Güvenli kelime sınırı regex ile değiştir
            import re
            pattern = re.compile(rf"\b{re.escape(old_symbol)}\b")
            updated, count = pattern.subn(new_symbol, original)

            if count > 0:
                # Sözdizimi geçerlilik denetimi
                try:
                    ast.parse(updated)
                except SyntaxError:
                    continue  # Geçersiz sözdizimi oluşturan dosya atlanır

                diff_lines = list(
                    difflib.unified_diff(
                        original.splitlines(keepends=True),
                        updated.splitlines(keepends=True),
                        fromfile=f"a/{rel_path}",
                        tofile=f"b/{rel_path}",
                        n=2,
                    )
                )
                diff = "".join(diff_lines)
                changes.append(
                    FileRenameChange(
                        path=rel_path,
                        old_content=original,
                        new_content=updated,
                        diff=diff,
                        occurrences=count,
                    )
                )
                total_replacements += count

        return SymbolRenamePlan(
            symbol_old=old_symbol,
            symbol_new=new_symbol,
            changes=tuple(changes),
            total_files=len(changes),
            total_replacements=total_replacements,
        )

