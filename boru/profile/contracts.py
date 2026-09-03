from typing import Protocol

from boru.profile.models import (
    ProfileUpdate,
    UserProfile,
)


class UserProfileRepository(
    Protocol
):
    def load(
        self,
    ) -> UserProfile:
        ...

    def save(
        self,
        profile: UserProfile,
    ) -> None:
        ...


class ProfileExtractor(
    Protocol
):
    def extract(
        self,
        user_message: str,
    ) -> list[ProfileUpdate]:
        ...


class ProfileService(
    Protocol
):
    def build_context(
        self,
    ) -> str:
        ...

    def observe(
        self,
        user_message: str,
    ) -> list[ProfileUpdate]:
        ...

    def get_name(
        self,
    ) -> str | None:
        ...

    def get_preference(
        self,
        key: str,
    ) -> str | None:
        ...


class ProfileQueryResolver(
    Protocol
):
    def resolve(
        self,
        user_message: str,
    ) -> str | None:
        ...