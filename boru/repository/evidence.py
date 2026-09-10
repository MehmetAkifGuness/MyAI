import hashlib
import re
from pathlib import Path

from boru.code_index import SafeCodeIndex
from boru.code_index.impact import SafeCodeImpactIndex
from boru.code_index.relationships import SafeCodeRelationshipIndex
from boru.repository.inspection import RepositoryInspector
from boru.tools.project_index import SafeProjectFileIndex
from boru.tools.workspace import ReadOnlyWorkspace


class TaskEvidence:
    """Bounded source windows and resolved import edges; never executes code."""

    PATH = re.compile(r"(?<![\w.-])(?:[\w.-]+[/\\])*[\w.-]+\.py\b")

    def __init__(self, root: Path, objective: str):
        self.root = root
        self.manifest = SafeProjectFileIndex(root, max_files=2000, max_depth=12).list_editable_files()
        self.reader = ReadOnlyWorkspace(root)
        self.explicit = tuple(dict.fromkeys(p.replace('\\', '/') for p in self.PATH.findall(objective)))
        missing = set(self.explicit) - set(self.manifest)
        if missing:
            raise ValueError("Açık dosya güvenli manifestte yok: " + ", ".join(sorted(missing)))
        self.reasons = {p: "açık dosya" for p in self.explicit}
        if not self.explicit:
            terms = [t for t in re.findall(r"\w{3,}", objective) if t.casefold() not in {
                "sorununu", "düzelt", "hatasını", "içindeki", "dosyasını", "geliştir", "testindeki",
            }]
            index = SafeCodeIndex(root, max_files=2000)
            for term in terms[:8]:
                for hit in index.search(term, max_results=4):
                    self.reasons.setdefault(hit.path, f"arama: {term}")
        self.seeds = tuple(self.reasons)[:4]
        relations = SafeCodeRelationshipIndex(root, max_files=2000)
        impact = SafeCodeImpactIndex(root, max_files=2000)
        for path in self.seeds:
            if not path.endswith('.py'):
                continue
            for item in relations.related_files(path, objective, max_results=5):
                self.reasons.setdefault(item.path, "import/çağrı: " + path + " → " + item.imported_via)
            for item in impact.impacted_files(path, max_results=8):
                if item.is_test:
                    self.reasons.setdefault(item.path, "ters import: " + path + f" (mesafe {item.distance})")
        self.candidates = tuple(p for p in self.reasons if p in self.manifest)[:24]
        self.windows = []
        self.fingerprints = {}
        self.characters = 0

    def read(self, path: str, start: int = 1) -> dict:
        if path not in self.candidates or type(start) is not int or start < 1:
            raise ValueError("Okuma adayı veya satır geçersiz.")
        if len(self.windows) >= 12 or self.characters >= 24000:
            raise ValueError("Kaynak okuma bütçesi doldu.")
        if any(w['path'] == path and w['start'] == start for w in self.windows):
            raise ValueError("Aynı pencere zaten okundu; mevcut kanıtı kullan.")
        content = self.reader.read_text_file(path)
        digest = hashlib.sha256(content.encode('utf-8')).hexdigest()
        if path in self.fingerprints and self.fingerprints[path] != digest:
            raise ValueError("Araştırma sırasında kaynak değişti.")
        lines = content.splitlines()
        if start > max(1, len(lines)):
            raise ValueError("Satır dosya dışında.")
        selected = []
        remaining = min(6000, 24000 - self.characters)
        for line in lines[start - 1:start + 159]:
            if len(line) + 1 > remaining:
                break
            selected.append(line)
            remaining -= len(line) + 1
        text = '\n'.join(selected)
        if lines and not selected:
            raise ValueError("Kaynak satırı okuma bütçesine sığmıyor.")
        window = {'path': path, 'start': start, 'text': text, 'total_lines': len(lines)}
        self.fingerprints[path] = digest
        self.characters += len(text)
        self.windows.append(window)
        return window

    def verify_citation(self, citation: dict) -> None:
        if not isinstance(citation, dict) or set(citation) != {'path', 'line', 'quote'}:
            raise ValueError("Kanıt path, line, quote gerektirir.")
        path, line, quote = citation['path'], citation['line'], citation['quote']
        if type(line) is not int or not isinstance(quote, str) or not quote.strip():
            raise ValueError("Kanıt satırı veya alıntısı boş/geçersiz.")
        for window in self.windows:
            lines = window['text'].splitlines()
            offset = line - window['start']
            if path == window['path'] and 0 <= offset < len(lines) and quote in lines[offset]:
                return
        raise ValueError('Alıntı okunmuş kaynak satırında bulunamadı: ' + str(citation)[:300])

    def numbered_windows(self):
        return [dict(path=w['path'], total_lines=w['total_lines'], source='\n'.join(
            f'{w["start"] + i}: {text}' for i, text in enumerate(w['text'].splitlines())
        )) for w in self.windows]

    def assert_current(self):
        for path, digest in self.fingerprints.items():
            now = hashlib.sha256(self.reader.read_text_file(path).encode('utf-8')).hexdigest()
            if now != digest:
                raise ValueError("Araştırma sırasında kaynak değişti: " + path)

    @staticmethod
    def is_test(path):
        return RepositoryInspector._is_test(path)
