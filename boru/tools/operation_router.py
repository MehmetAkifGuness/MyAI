from collections.abc import Sequence
from typing import Protocol


class PendingAwareResolver(Protocol):
    @property
    def has_pending(self) -> bool:
        ...

    def resolve(self, user_message: str) -> str | None:
        ...


class ExclusiveOperationCoordinator:
    """Aynı anda yalnızca bir onay gerektiren işlem akışını etkin tutar."""

    _ORPHAN_CONTROL_COMMANDS = {
        "onayla",
        "yazmayı onayla",
        "dosya yazımını onayla",
        "değişikliği onayla",
        "düzenlemeyi onayla",
        "proje değişikliğini onayla",
        "silmeyi onayla",
        "git işlemini onayla",
        "git geri almayı onayla",
        "otomatik düzeltmeyi onayla",
        "kod değişikliğini onayla",
        "api isteğini onayla",
        "iptal",
        "vazgeç",
    }

    def __init__(self, resolvers: Sequence[PendingAwareResolver]) -> None:
        if not resolvers:
            raise ValueError("En az bir işlem resolver'ı gereklidir.")
        self._resolvers = tuple(resolvers)

    def resolve(self, user_message: str) -> str | None:
        active = tuple(resolver for resolver in self._resolvers if resolver.has_pending)
        if len(active) > 1:
            return (
                "Birden fazla onay akışı etkin görünüyor. Güvenlik için yeni işlem "
                "başlatılmadı; etkin işlemleri 'iptal' ile kapatın."
            )
        if active:
            return active[0].resolve(user_message)

        normalized = " ".join(user_message.casefold().strip().split()).rstrip(".!?")
        if normalized in self._ORPHAN_CONTROL_COMMANDS:
            return "Onay veya iptal bekleyen etkin bir işlem yok."

        for resolver in self._resolvers:
            response = resolver.resolve(user_message)
            if response is not None:
                return response
        return None
