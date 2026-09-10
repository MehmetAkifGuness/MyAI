"""
boru.code_index.graph_coordinator
=================================
Kullanıcıdan gelen 'bağımlılıklar: ...', 'sembol ara: ...' veya 'yeniden adlandır: ...'
komutlarını karşılayıp çift yönlü etki analizi ve çoklu dosya refactor
planları üreten doğrudan yanıt koordinatörü.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Callable

from boru.code_index.graph import ProjectDependencyGraph, SymbolRenamePlan


class DependencyGraphCoordinator:
    """
    DirectResponseResolver protokolünü uygular.
    Bağımlılık haritası, sembol araması ve çoklu dosya refactor komutlarını işler.
    """

    _DEP_REGEX = re.compile(
        r"^\s*(?:bağımlılıklar|bagimliliklar|etki\s+analizi|bağımlılık\s+analizi)\s*:\s*(?P<target>.+)$",
        re.IGNORECASE,
    )

    _SYMBOL_REGEX = re.compile(
        r"^\s*(?:sembol\s+ara|sembol\s+bul|fonksiyon\s+ara|sınıf\s+ara)\s*:\s*(?P<symbol>\w+)$",
        re.IGNORECASE,
    )

    _RENAME_REGEX = re.compile(
        r"^\s*(?:yeniden\s+adlandır|yeniden\s+adlandir|refactor)\s*:\s*(?P<path>[^|]+)\|\s*(?P<old>\w+)\s*->\s*(?P<new>\w+)$",
        re.IGNORECASE,
    )

    def __init__(
        self,
        project_root: str | Path = ".",
        graph: ProjectDependencyGraph | None = None,
    ) -> None:
        self._root = Path(project_root).resolve()
        self._graph = graph or ProjectDependencyGraph(self._root)
        self._pending_plan: SymbolRenamePlan | None = None

    def resolve(self, user_message: str) -> str | None:
        raw = user_message.strip()

        # Onay bekleme kontrolü
        if self._pending_plan is not None:
            if raw.casefold() in {"refactor onayla", "değişikliği onayla", "degisikligi onayla"}:
                return self._apply_pending_plan()
            elif raw.casefold() in {"iptal", "vazgeç", "vazgec"}:
                self._pending_plan = None
                return "Refactor işlemi iptal edildi."

        # 1. Bağımlılık ve Etki Analizi
        dep_match = self._DEP_REGEX.match(raw)
        if dep_match:
            target_path = dep_match.group("target").strip("'\"` ")
            return self._handle_dependencies(target_path)

        # 2. Sembol Arama
        sym_match = self._SYMBOL_REGEX.match(raw)
        if sym_match:
            symbol_name = sym_match.group("symbol").strip()
            return self._handle_symbol_search(symbol_name)

        # 3. Çoklu Dosya Yeniden Adlandırma (Refactor)
        rename_match = self._RENAME_REGEX.match(raw)
        if rename_match:
            path = rename_match.group("path").strip("'\"` ")
            old_sym = rename_match.group("old").strip()
            new_sym = rename_match.group("new").strip()
            return self._handle_rename_plan(path, old_sym, new_sym)

        return None

    def _handle_dependencies(self, target_path: str) -> str:
        clean_path = target_path.replace("\\", "/")
        full_path = self._root / clean_path
        if not full_path.exists():
            return f"❌ Belirtilen dosya bulunamadı: `{clean_path}`"

        report = self._graph.analyze_file(clean_path)
        lines = [
            f"🕸️ BAĞIMLILIK VE ETKİ HARİTASI: `{report.target_path}`",
            "",
            f"⬆️ İçe Aktardığı Proje Modülleri ({len(report.forward_imports)} dosya):",
        ]
        if report.forward_imports:
            for imp in report.forward_imports:
                lines.append(f"  - `{imp}`")
        else:
            lines.append("  (başka bir proje içi modül import edilmiyor)")

        lines.extend([
            "",
            f"⬇️ Bu Dosyayı Kullanan Modüller ({len(report.reverse_dependents)} dosya):",
        ])
        if report.reverse_dependents:
            for dep in report.reverse_dependents:
                lines.append(f"  - `{dep}`")
        else:
            lines.append("  (bu dosyaya doğrudan bağımlı modül bulunamadı)")

        lines.extend([
            "",
            f"🧪 İlişkili Test Dosyaları ({len(report.associated_tests)} test):",
        ])
        if report.associated_tests:
            for tst in report.associated_tests:
                lines.append(f"  - `{tst}`")
        else:
            lines.append("  (ilişkili bir test bulunamadı - 'test üret: " + report.target_path + "' ile üretebilirsiniz)")

        return "\n".join(lines)

    def _handle_symbol_search(self, symbol_name: str) -> str:
        results = self._graph.find_symbol_references(symbol_name)
        if not results:
            return f"🔍 Projede `{symbol_name}` adında herhangi bir sınıf, fonksiyon veya referans bulunamadı."

        by_file: dict[str, list] = {}
        for item in results:
            by_file.setdefault(item.path, []).append(item)

        lines = [
            f"🔍 SEMBOL ARAMA RAPORU: `{symbol_name}`",
            f"Toplam {len(results)} referans, {len(by_file)} farklı dosyada bulundu:",
            "",
        ]

        for file_path, items in by_file.items():
            lines.append(f"📁 `{file_path}`:")
            for it in items:
                lines.append(f"  - [Satır {it.line_number}] ({it.kind}): `{it.snippet}`")

        return "\n".join(lines)

    def _handle_rename_plan(self, path: str, old_symbol: str, new_symbol: str) -> str:
        plan = self._graph.plan_symbol_rename(path, old_symbol, new_symbol)
        if not plan.changes:
            return f"⚠️ `{path}` ve bağımlılıklarında `{old_symbol}` sembolü için değiştirilecek referans bulunamadı."

        self._pending_plan = plan
        lines = [
            f"🔄 ÇOKLU DOSYA REFACTOR PLANI: `{old_symbol}` ➔ `{new_symbol}`",
            f"Etkilenen Dosyalar: {plan.total_files} adet",
            f"Toplam Değişiklik: {plan.total_replacements} referans",
            "",
            "📝 Önerilen Değişiklikler:",
        ]

        for change in plan.changes:
            lines.extend([
                f"--- `{change.path}` ({change.occurrences} yer) ---",
                change.diff.strip(),
                "",
            ])

        lines.extend([
            "⚠️ Onaylamak için: 'refactor onayla'",
            "❌ İptal etmek için: 'iptal' yazın.",
        ])

        return "\n".join(lines)

    def _apply_pending_plan(self) -> str:
        plan = self._pending_plan
        self._pending_plan = None
        if not plan:
            return "Uygulanacak bekleyen bir refactor planı yok."

        applied_files = []
        for change in plan.changes:
            target_file = self._root / change.path
            try:
                target_file.write_text(change.new_content, encoding="utf-8")
                applied_files.append(change.path)
            except Exception as err:
                return f"❌ Refactor uygulanırken `{change.path}` dosyasına yazılamadı: {err}"

        lines = [
            f"✔ REFACTOR BAŞARIYLA UYGULANDI ({plan.symbol_old} ➔ {plan.symbol_new})",
            f"Güncellenen dosya sayısı: {len(applied_files)}",
            "",
            "Dosyalar:",
        ]
        for f in applied_files:
            lines.append(f"  - `{f}`")

        lines.extend([
            "",
            "💡 Değişikliklerin doğruluğunu test etmek için `pytest` çalıştırabilirsiniz.",
        ])
        return "\n".join(lines)

