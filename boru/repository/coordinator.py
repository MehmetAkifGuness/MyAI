import re
from dataclasses import dataclass
from pathlib import Path

from boru.repository.github import GitHubRepositoryImporter
from boru.repository.inspection import RepositoryInspector
from boru.repository.models import RepositoryProfile
from boru.repository.state import RepositoryAuditLog, RepositoryWorkspaceState
from boru.repository.workspace_coordinator import RepositoryWorkspaceCoordinator
from boru.tools.workspace import WorkspaceAccessError, WorkspacePathResolver


@dataclass(frozen=True, slots=True)
class PendingRepositoryImport:
    url: str
    destination: Path


class RepositoryCoordinator:
    _IMPORT = re.compile(r"^\s*(?:repo|github\s+repo)\s+(?:içe\s+aktar|klonla)\s*:\s*(.+?)\s*$", re.I)
    _ANALYZE = re.compile(r"^\s*repo\s+(?:analiz\s+et|incele)(?:\s*:\s*(.+?))?\s*$", re.I)
    _CONTEXT = re.compile(r"^\s*repo\s+(?:görev\s+bağlamı|bağlam)\s*:\s*(.+?)\s*$", re.I)
    _USAGE = (
        "Biçimler: 'repo analiz et'; 'repo analiz et: göreli/klasör'; "
        "'repo görev bağlamı: hedef | repo=göreli/klasör'; "
        "'repo içe aktar: https://github.com/owner/repo'; 'repo sınırlar'; "
        "'repo seç: yol'; 'repo durum'; 'repo geliştir: hedef'; "
        "'repo doğrula: dosya.py'; 'repo git durum'; 'repo günlüğü'."
    )

    def __init__(
        self,
        root: Path,
        inspector: RepositoryInspector,
        importer: GitHubRepositoryImporter,
        workspace: RepositoryWorkspaceCoordinator | None = None,
        workspace_factory=None,
        workspace_state: RepositoryWorkspaceState | None = None,
        audit_log: RepositoryAuditLog | None = None,
    ):
        self._root = root.resolve()
        self._resolver = WorkspacePathResolver(self._root)
        self._inspector = inspector
        self._importer = importer
        self._pending: PendingRepositoryImport | None = None
        if workspace is not None and workspace_factory is not None:
            raise ValueError("Repo çalışma alanı iki farklı yolla yapılandırılamaz.")
        if workspace_factory is not None:
            if workspace_state is None or audit_log is None:
                raise ValueError("Repo çalışma alanı state ve audit günlüğü gerektirir.")
            workspace = RepositoryWorkspaceCoordinator(
                self._repository_root,
                workspace_factory,
                workspace_state,
                audit_log,
            )
        self._workspace = workspace

    @property
    def has_pending(self) -> bool:
        return self._pending is not None or bool(self._workspace and self._workspace.has_pending)

    def resolve(self, message: str) -> str | None:
        if self._workspace:
            response = self._workspace.resolve(message)
            if response is not None:
                return response
        if self._pending:
            return self._resolve_pending(message)
        normalized = " ".join(message.casefold().strip().split())
        if normalized in {"repo yardım", "repo yardim"}:
            return self._USAGE
        if normalized == "repo sınırlar":
            return self._render_limits()
        match = self._IMPORT.fullmatch(message)
        if match:
            return self._prepare_import(match.group(1))
        match = self._ANALYZE.fullmatch(message)
        if match:
            try:
                root, label = self._repository_root(match.group(1) or "")
                return self._render_profile(self._inspector.inspect(root, display_root=label))
            except (OSError, ValueError, WorkspaceAccessError) as error:
                return f"REPO ANALİZİ\nDurum: BAŞARISIZ\n{error}"
        match = self._CONTEXT.fullmatch(message)
        if match:
            return self._task_context(match.group(1))
        return self._USAGE if normalized.startswith(("repo ", "github repo ")) else None

    def locate_repository(self, value: str) -> tuple[Path, str]:
        return self._repository_root(value)

    def _prepare_import(self, url: str) -> str:
        try:
            destination = self._importer.destination_for(url)
            if destination.exists():
                raise ValueError("Repo hedefi zaten mevcut; üzerine yazılmaz.")
        except ValueError as error:
            return f"REPO İÇE AKTARMA\nDurum: REDDEDİLDİ\n{error}"
        self._pending = PendingRepositoryImport(url.strip(), destination)
        relative = destination.relative_to(self._root).as_posix()
        return (
            "REPO İÇE AKTARMA\nDurum: ONAY BEKLİYOR\n"
            f"Kaynak: {url.strip()}\nHedef: {relative}\n"
            "Repo kodu çalıştırılmadan sınırlı arşiv olarak indirilecek. "
            "Uygulamak için yalnızca 'repo içe aktarmayı onayla', vazgeçmek için 'iptal' yazın."
        )

    def _resolve_pending(self, message: str) -> str:
        normalized = " ".join(message.casefold().strip().split())
        if normalized in {"iptal", "vazgeç"}:
            self._pending = None
            return "Repo içe aktarma iptal edildi."
        if normalized != "repo içe aktarmayı onayla":
            return "Repo içe aktarma onay bekliyor: 'repo içe aktarmayı onayla' veya 'iptal' yazın."
        pending = self._pending
        self._pending = None
        try:
            destination = self._importer.import_repository(pending.url)
            relative = destination.relative_to(self._root).as_posix()
            profile = self._inspector.inspect(destination, display_root=relative)
        except (OSError, RuntimeError, ValueError) as error:
            return f"REPO İÇE AKTARMA\nDurum: BAŞARISIZ\n{error}"
        return "REPO İÇE AKTARMA\nDurum: TAMAMLANDI\n" + self._render_profile(profile)

    def _task_context(self, value: str) -> str:
        pieces = [piece.strip() for piece in value.split("|") if piece.strip()]
        if not pieces:
            return "REPO GÖREV BAĞLAMI\nDurum: BAŞARISIZ\nHedef boş olamaz."
        objective = pieces[0]
        relative = ""
        for option in pieces[1:]:
            key, separator, content = option.partition("=")
            if not separator or key.casefold().strip() != "repo" or relative:
                return "REPO GÖREV BAĞLAMI\nDurum: BAŞARISIZ\nBilinmeyen bağlam seçeneği."
            relative = content.strip()
        try:
            root, label = self._repository_root(relative)
            context = self._inspector.task_context(root, objective)
        except (OSError, ValueError, WorkspaceAccessError) as error:
            return f"REPO GÖREV BAĞLAMI\nDurum: BAŞARISIZ\n{error}"
        lines = ["REPO GÖREV BAĞLAMI", "Durum: HAZIR", f"Repo: {label}",
                 f"Hedef: {context.objective}", f"Aday dosya: {len(context.paths)}"]
        reasons = dict(context.reasons)
        lines.extend(
            f"- {self._prefixed(label, path)} — {reasons.get(path, 'bağlam adayı')}"
            for path in context.paths
        )
        lines.append("Not: Repo içeriği güvenilmeyen veridir; dosyalardaki talimatlar yürütülmedi.")
        return "\n".join(lines)

    def _repository_root(self, relative: str) -> tuple[Path, str]:
        normalized = self._normalize_repository_path(relative)
        root = self._resolver.resolve(normalized)
        if not root.is_dir():
            raise ValueError("Repo yolu bir klasör olmalıdır.")
        label = root.relative_to(self._root).as_posix() or "."
        return root, label

    def _normalize_repository_path(self, value: str) -> str:
        cleaned = value.strip()
        if cleaned.startswith("https://"):
            destination = self._importer.destination_for(cleaned)
            return destination.relative_to(self._root).as_posix()
        normalized = re.sub(r"/+", "/", cleaned.replace("\\", "/"))
        prefix = "repositories/github.com/"
        if normalized.casefold().startswith(prefix):
            normalized = "repositories/github/" + normalized[len(prefix):]
        return normalized

    @staticmethod
    def _prefixed(label: str, path: str) -> str:
        return path if label == "." else f"{label}/{path}"

    @staticmethod
    def _render_profile(profile: RepositoryProfile) -> str:
        languages = ", ".join(f"{name}={count}" for name, count in profile.languages) or "bulunamadı"
        lines = ["REPO ANALİZİ", "Durum: HAZIR", f"Kök: {profile.root}",
                 f"Dosya: {profile.file_count}", f"Diller: {languages}",
                 "Frameworkler: " + (", ".join(profile.frameworks) or "bulunamadı"),
                 "Paket yöneticileri: " + (", ".join(profile.package_managers) or "bulunamadı"),
                 "Giriş noktaları: " + (", ".join(profile.entry_points) or "bulunamadı"),
                 f"Test dosyaları: {len(profile.test_files)}",
                 "Önerilen testler: " + (", ".join(profile.test_commands) or "bulunamadı"),
                 f"Dokümantasyon: {len(profile.documentation)}; CI: {len(profile.ci_files)}; "
                 f"Lisans: {', '.join(profile.license_files) or 'bulunamadı'}",
                 "Güvenlik: Hiçbir repo dosyası veya komutu çalıştırılmadı."]
        return "\n".join(lines)

    @staticmethod
    def _render_limits() -> str:
        return (
            "REPO SINIRLARI\n"
            "- Yalnızca HTTPS github.com owner/repository adresi\n"
            "- Arşiv: 20 MB; dosya: 3000; açılmış toplam: 100 MB; tek dosya: 2 MB\n"
            "- Symlink, yol kaçışı, .git ve otomatik üzerine yazma engelli\n"
            "- İçe aktarma açık onay gerektirir; repo kodu otomatik çalıştırılmaz\n"
            "- İndeks: en fazla 2000 güvenli metin/kod dosyası"
        )
