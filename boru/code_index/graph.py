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
            except Exception:
                continue

        results.sort(key=lambda x: (x.path, x.line_number))
        return tuple(results)

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

