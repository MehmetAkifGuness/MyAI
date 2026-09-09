import re
import stat
from io import BytesIO
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zipfile import BadZipFile, ZipFile


class _RestrictedGitHubRedirects(HTTPRedirectHandler):
    _HOSTS = {"api.github.com", "github.com", "codeload.github.com", "objects.githubusercontent.com"}

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        if parsed.scheme != "https" or parsed.hostname not in self._HOSTS:
            raise RuntimeError("GitHub indirmesi izin verilmeyen adrese yönlendirildi.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class GitHubRepositoryPolicy:
    _SEGMENT = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,99})")

    @classmethod
    def parse(cls, value: str) -> tuple[str, str]:
        parsed = urlparse(value.strip())
        if (
            parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.port is not None
            or parsed.username or parsed.password or parsed.query or parsed.fragment
        ):
            raise ValueError("Yalnızca HTTPS github.com depo adreslerine izin verilir.")
        parts = tuple(part for part in parsed.path.split("/") if part)
        if len(parts) != 2:
            raise ValueError("GitHub adresi owner/repository biçiminde olmalıdır.")
        owner, repository = parts
        repository = repository.removesuffix(".git")
        if not cls._SEGMENT.fullmatch(owner) or not cls._SEGMENT.fullmatch(repository):
            raise ValueError("GitHub owner veya repository adı geçersiz.")
        return owner, repository


class GitHubRepositoryImporter:
    """Downloads a bounded GitHub archive and extracts it without executing repository code."""

    def __init__(
        self,
        workspace_root: Path,
        *,
        downloader=None,
        max_archive_bytes: int = 20 * 1024 * 1024,
        max_files: int = 3000,
        max_extracted_bytes: int = 100 * 1024 * 1024,
        max_file_bytes: int = 2 * 1024 * 1024,
    ):
        self._root = workspace_root.resolve()
        self._downloader = downloader or self._download
        self._max_archive_bytes = max_archive_bytes
        self._max_files = max_files
        self._max_extracted_bytes = max_extracted_bytes
        self._max_file_bytes = max_file_bytes

    def destination_for(self, url: str) -> Path:
        owner, repository = GitHubRepositoryPolicy.parse(url)
        return self._root / "repositories" / "github" / owner / repository

    def import_repository(self, url: str) -> Path:
        owner, repository = GitHubRepositoryPolicy.parse(url)
        destination = self.destination_for(url)
        if destination.exists():
            raise ValueError("Repo hedefi zaten mevcut; mevcut içerik otomatik üzerine yazılmaz.")
        archive = self._downloader(
            f"https://api.github.com/repos/{owner}/{repository}/zipball"
        )
        if not isinstance(archive, bytes) or not archive or len(archive) > self._max_archive_bytes:
            raise ValueError("GitHub arşivi boş veya boyut sınırını aşıyor.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".boru-import-", dir=destination.parent) as temporary:
            extracted = Path(temporary) / "content"
            extracted.mkdir()
            self._extract(archive, extracted)
            extracted.replace(destination)
        return destination

    def _extract(self, archive: bytes, root: Path) -> None:
        try:
            zipped = ZipFile(BytesIO(archive))
        except BadZipFile as error:
            raise ValueError("GitHub yanıtı geçerli ZIP arşivi değil.") from error
        with zipped:
            members = [item for item in zipped.infolist() if not item.is_dir()]
            if not members or len(members) > self._max_files:
                raise ValueError("Repo dosya sayısı boş veya güvenli sınırı aşıyor.")
            total = 0
            for item in members:
                total += item.file_size
                if item.file_size > self._max_file_bytes or total > self._max_extracted_bytes:
                    raise ValueError("Repo açılmış içerik boyutu güvenli sınırı aşıyor.")
                mode = item.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise ValueError("Repo arşivinde sembolik bağlantıya izin verilmez.")
                normalized = item.filename.replace("\\", "/")
                archive_path = PurePosixPath(normalized)
                if archive_path.is_absolute():
                    raise ValueError("Repo arşivinde mutlak yola izin verilmez.")
                parts = archive_path.parts
                relative = parts[1:] if len(parts) > 1 else ()
                if not relative:
                    continue
                if any(
                    part in {"", ".", "..", ".git"} or ":" in part
                    or any(ord(character) < 32 for character in part)
                    for part in relative
                ):
                    raise ValueError("Repo arşivinde güvenli olmayan dosya yolu bulundu.")
                target = root.joinpath(*relative)
                resolved = target.resolve(strict=False)
                if not resolved.is_relative_to(root.resolve()):
                    raise ValueError("Repo arşivi hedef klasör dışına çıkmaya çalıştı.")
                target.parent.mkdir(parents=True, exist_ok=True)
                with zipped.open(item) as source, target.open("xb") as output:
                    content = source.read(self._max_file_bytes + 1)
                    if len(content) > self._max_file_bytes:
                        raise ValueError("Repo dosyası güvenli boyut sınırını aşıyor.")
                    output.write(content)
        if not any(root.rglob("*")):
            raise ValueError("Repo arşivinde kullanılabilir dosya bulunamadı.")

    def _download(self, url: str) -> bytes:
        request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "Boru/9.0"})
        opener = build_opener(_RestrictedGitHubRedirects())
        try:
            with opener.open(request, timeout=30) as response:
                data = response.read(self._max_archive_bytes + 1)
        except (OSError, TimeoutError) as error:
            raise RuntimeError(f"GitHub deposu indirilemedi: {error}") from error
        return data
