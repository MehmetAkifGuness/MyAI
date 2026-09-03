import re

from boru.memory.models import (
    StructuredMemoryFact,
)


class RuleBasedMemoryStructurer:
    """
    Yaygın proje teknoloji cümlelerini
    subject/relation/value üçlüsüne dönüştürür.

    Emin olmadığı cümleleri yapılandırmaz.
    """

    _TEST_FRAMEWORKS = {
        "pytest",
        "unittest",
        "junit",
        "junit5",
        "testng",
        "jest",
        "vitest",
        "mocha",
    }

    _BACKEND_FRAMEWORKS = {
        "fastapi",
        "flask",
        "django",
        "spring",
        "spring boot",
        "express",
        "nestjs",
    }

    _DATABASES = {
        "postgres",
        "postgresql",
        "mysql",
        "mariadb",
        "sqlite",
        "mongodb",
        "redis",
    }

    _STATE_MANAGEMENT = {
        "riverpod",
        "provider",
        "bloc",
        "getx",
        "redux",
    }

    _SCOPED_SUBJECT = (
        r"(?P<subject>.+?)\s+"
        r"(?:projem|uygulamam|servisim|sistemim)"
    )

    _EXPLICIT_PATTERNS = (
        (
            re.compile(
                (
                    rf"^{_SCOPED_SUBJECT}\s+"
                    r"(?:artık\s+)?"
                    r"test(?:lerde|lerdeki|"
                    r"\s+framework(?:ü|u)?"
                    r"\s+olarak)\s+"
                    r"(?P<value>.+?)\s+"
                    r"kullanıyor(?:um)?"
                    r"[.!]?$"
                ),
                re.IGNORECASE,
            ),
            "test_framework",
        ),
        (
            re.compile(
                (
                    rf"^{_SCOPED_SUBJECT}\s+"
                    r"(?:artık\s+)?"
                    r"veritabanı\s+olarak\s+"
                    r"(?P<value>.+?)\s+"
                    r"kullanıyor(?:um)?"
                    r"[.!]?$"
                ),
                re.IGNORECASE,
            ),
            "database",
        ),
        (
            re.compile(
                (
                    rf"^{_SCOPED_SUBJECT}\s+"
                    r"(?:artık\s+)?"
                    r"backend"
                    r"(?:\s+framework(?:ü|u)?)?"
                    r"\s+olarak\s+"
                    r"(?P<value>.+?)\s+"
                    r"kullanıyor(?:um)?"
                    r"[.!]?$"
                ),
                re.IGNORECASE,
            ),
            "backend_framework",
        ),
        (
            re.compile(
                (
                    rf"^{_SCOPED_SUBJECT}\s+"
                    r"(?:artık\s+)?"
                    r"state\s+management\s+"
                    r"olarak\s+"
                    r"(?P<value>.+?)\s+"
                    r"kullanıyor(?:um)?"
                    r"[.!]?$"
                ),
                re.IGNORECASE,
            ),
            "state_management",
        ),
        (
            re.compile(
                (
                    r"^(?P<subject>.+?)\s+"
                    r"servisimin\s+testleri\s+"
                    r"(?P<value>.+?)\s+"
                    r"ile\s+çalışıyor(?:lar)?"
                    r"[.!]?$"
                ),
                re.IGNORECASE,
            ),
            "test_framework",
        ),
    )

    _GENERIC_SCOPE_PATTERN = re.compile(
        (
            rf"^{_SCOPED_SUBJECT}\s+"
            r"(?:artık\s+)?"
            r"(?P<value>.+?)\s+"
            r"kullanıyor(?:um)?"
            r"[.!]?$"
        ),
        re.IGNORECASE,
    )

    _POSSESSIVE_NAMED_SUBJECT_PATTERN = re.compile(
        (
            r"^(?P<subject>.+?)"
            r"[’'](?:m|ım|im|um|üm)\s+"
            r"(?:artık\s+)?"
            r"(?P<value>.+?)\s+"
            r"kullanıyor(?:um)?"
            r"[.!]?$"
        ),
        re.IGNORECASE,
    )

    def structure(
        self,
        content: str,
    ) -> StructuredMemoryFact | None:
        text = self._clean(
            content
        )

        if not text:
            return None

        for pattern, relation in self._EXPLICIT_PATTERNS:
            match = pattern.fullmatch(
                text
            )

            if match:
                return self._build_fact(
                    subject=match.group(
                        "subject"
                    ),
                    relation=relation,
                    value=match.group(
                        "value"
                    ),
                )

        for pattern in (
            self._GENERIC_SCOPE_PATTERN,
            self._POSSESSIVE_NAMED_SUBJECT_PATTERN,
        ):
            match = pattern.fullmatch(
                text
            )

            if not match:
                continue

            value = self._clean_value(
                match.group(
                    "value"
                )
            )

            relation = self._infer_relation(
                value
            )

            if relation is None:
                return None

            return self._build_fact(
                subject=match.group(
                    "subject"
                ),
                relation=relation,
                value=value,
            )

        return None

    def _infer_relation(
        self,
        value: str,
    ) -> str | None:
        folded = value.casefold()

        if folded in self._TEST_FRAMEWORKS:
            return "test_framework"

        if folded in self._BACKEND_FRAMEWORKS:
            return "backend_framework"

        if folded in self._DATABASES:
            return "database"

        if folded in self._STATE_MANAGEMENT:
            return "state_management"

        return None

    @classmethod
    def _build_fact(
        cls,
        subject: str,
        relation: str,
        value: str,
    ) -> StructuredMemoryFact | None:
        cleaned_subject = (
            cls._clean_subject(
                subject
            )
        )

        cleaned_value = (
            cls._clean_value(
                value
            )
        )

        if (
            not cleaned_subject
            or not cleaned_value
        ):
            return None

        return StructuredMemoryFact(
            subject=cleaned_subject,
            relation=relation,
            value=cleaned_value,
        )

    @staticmethod
    def _clean(
        value: str,
    ) -> str:
        return " ".join(
            value.strip().split()
        )

    @staticmethod
    def _clean_subject(
        value: str,
    ) -> str:
        return " ".join(
            value
            .strip(
                " \t\r\n,;:-.!?"
            )
            .split()
        )[:120]

    @staticmethod
    def _clean_value(
        value: str,
    ) -> str:
        return " ".join(
            value
            .strip(
                " \t\r\n,;:-.!?"
            )
            .split()
        )[:120]