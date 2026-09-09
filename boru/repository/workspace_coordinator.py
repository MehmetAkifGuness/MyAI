import re
from pathlib import Path

from boru.repository.state import RepositoryAuditLog, RepositoryWorkspaceState


class RepositoryWorkspaceCoordinator:
    _SELECT = re.compile(r"^\s*repo\s+(?:seç|sec)\s*:\s*(.+?)\s*$", re.I)
    _DEVELOP = re.compile(r"^\s*repo\s+(?:geliştir|gelistir)\s*:\s*(.+?)\s*$", re.I | re.S)
    _VERIFY = re.compile(r"^\s*repo\s+(?:doğrula|dogrula)\s*:\s*(.+?)\s*$", re.I)
    _GIT = re.compile(r"^\s*repo\s+git\s+(.+?)\s*$", re.I | re.S)

    def __init__(self, locate, runtime_factory, state: RepositoryWorkspaceState, audit: RepositoryAuditLog):
        self._locate = locate
        self._runtime_factory = runtime_factory
        self._state = state
        self._audit = audit
        self._runtime = None
        self._label: str | None = None
        saved = state.load()
        if saved:
            try:
                self._activate(saved, persist=False, event="workspace_restored")
            except (OSError, RuntimeError, ValueError):
                self._audit.record("workspace_restore_failed", saved)

    @property
    def has_pending(self) -> bool:
        return bool(self._runtime and self._runtime.has_pending)

    def resolve(self, message: str) -> str | None:
        normalized = " ".join(message.casefold().strip().split()).rstrip(".!?")
        if self.has_pending and (
            self._SELECT.fullmatch(message)
            or normalized in {"repo bırak", "repo birak"}
        ):
            return "REPO ÇALIŞMA ALANI\nDurum: DURDU\nBekleyen işlem varken repo değiştirilemez."
        if self._runtime and self._runtime.coding.has_pending:
            result = self._runtime.coding.resolve(message)
            self._audit.record("coding_control", self._label or "", self._status(result))
            return result
        if self._runtime and self._runtime.git and self._runtime.git.has_pending:
            result = self._runtime.git.resolve(message)
            self._audit.record("git_control", self._label or "", self._status(result))
            return result

        match = self._SELECT.fullmatch(message)
        if match:
            return self._select(match.group(1))
        if normalized in {"repo durum", "repo çalışma alanı", "repo calisma alani"}:
            return self._render_status()
        if normalized in {"repo bırak", "repo birak"}:
            return self._leave()
        if normalized in {"repo günlüğü", "repo gunlugu"}:
            return self._render_audit()
        match = self._DEVELOP.fullmatch(message)
        if match:
            return self._develop(match.group(1))
        match = self._VERIFY.fullmatch(message)
        if match:
            return self._verify(match.group(1))
        match = self._GIT.fullmatch(message)
        if match:
            return self._git(match.group(1))
        return None

    def _select(self, value: str) -> str:
        if self.has_pending:
            return "REPO ÇALIŞMA ALANI\nDurum: DURDU\nBekleyen işlem varken repo değiştirilemez."
        try:
            self._activate(value, persist=True, event="workspace_selected")
        except (OSError, RuntimeError, ValueError) as error:
            return self._selection_error(value, error)
        return self._render_status()

    def _activate(self, value: str, *, persist: bool, event: str) -> None:
        root, label = self._locate(value)
        runtime = self._runtime_factory(root)
        if persist:
            self._state.save(label)
        self._runtime = runtime
        self._label = label
        self._audit.record(event, label)

    def _leave(self) -> str:
        if self.has_pending:
            return "REPO ÇALIŞMA ALANI\nDurum: DURDU\nBekleyen işlem varken repo bırakılamaz."
        label = self._label or ""
        try:
            self._state.clear()
        except OSError as error:
            return f"REPO ÇALIŞMA ALANI\nDurum: BAŞARISIZ\n{error}"
        self._runtime = None
        self._label = None
        self._audit.record("workspace_left", label)
        return "REPO ÇALIŞMA ALANI\nDurum: KAPALI\nAktif repo bırakıldı."

    def _develop(self, objective: str) -> str:
        if self._runtime is None:
            return self._missing()
        self._audit.record("coding_requested", self._label or "", "request_received")
        return self._runtime.coding.resolve("kodla: " + objective)

    def _verify(self, value: str) -> str:
        if self._runtime is None:
            return self._missing()
        paths = tuple(dict.fromkeys(path.strip().replace("\\", "/") for path in value.split(",") if path.strip()))
        if not 1 <= len(paths) <= 12:
            return "REPO DOĞRULAMA\nDurum: BAŞARISIZ\n1-12 dosya belirtilmelidir."
        result = self._runtime.validate_paths(paths)
        self._audit.record("verification", self._label or "", self._status(result))
        return "REPO DOĞRULAMA\n" + result

    def _git(self, command: str) -> str:
        if self._runtime is None:
            return self._missing()
        if self._runtime.git is None:
            return (
                "REPO GIT\nDurum: KULLANILAMIYOR\n"
                "Seçili çalışma alanında .git metadata yok. Güvenli arşiv içe aktarımları "
                "Git geçmişi olmadan açılır."
            )
        result = self._runtime.git.resolve("git " + command.strip())
        self._audit.record("git_requested", self._label or "", self._status(result))
        return result

    def _render_status(self) -> str:
        if self._runtime is None:
            return "REPO ÇALIŞMA ALANI\nDurum: KAPALI\nAktif repo yok. 'repo seç: yol' kullanın."
        git = "hazır" if self._runtime.git else "metadata yok"
        return (
            "REPO ÇALIŞMA ALANI\nDurum: HAZIR\n"
            f"Kök: {self._label}\nGit: {git}\n"
            "Kod, test, güvenlik ve inceleme işlemleri bu kökle sınırlandırıldı."
        )

    def _render_audit(self) -> str:
        records = self._audit.read()[-20:]
        lines = ["REPO İŞLEM GÜNLÜĞÜ", f"Kayıt: {len(records)}"]
        lines.extend(
            f"- {item.get('time', '?')} {item.get('event', '?')} [{item.get('root', '')}] "
            f"{item.get('detail', '')}".rstrip()
            for item in records
        )
        return "\n".join(lines)

    @staticmethod
    def _status(result: str | None) -> str:
        if not result:
            return "no_response"
        for line in result.splitlines():
            if line.startswith("Durum:"):
                return line
        return result.splitlines()[0][:120]

    @staticmethod
    def _missing() -> str:
        return "REPO ÇALIŞMA ALANI\nDurum: KAPALI\nÖnce 'repo seç: yol' kullanın."

    @staticmethod
    def _selection_error(value: str, error: Exception) -> str:
        cleaned = re.sub(r"/+", "/", value.strip().replace("\\", "/"))
        github = re.fullmatch(
            r"repositories/(?:github|github\.com)/([^/]+)/([^/]+)",
            cleaned,
            re.I,
        )
        if cleaned.casefold().startswith("https://github.com/"):
            url = cleaned
        elif github:
            url = f"https://github.com/{github.group(1)}/{github.group(2)}"
        else:
            url = ""
        hint = ""
        if url:
            hint = (
                "\nRepo kopyası içe aktarılmamış veya silinmiş olabilir. Önce şu komutu kullanın:\n"
                f"repo içe aktar: {url}"
            )
        return f"REPO ÇALIŞMA ALANI\nDurum: BAŞARISIZ\n{error}{hint}"
