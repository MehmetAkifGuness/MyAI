from boru.profile.contracts import (
    ProfileService,
)


class ProfileObserver:
    def __init__(
        self,
        profile_service: ProfileService,
    ):
        self._profile_service = (
            profile_service
        )

    def observe(
        self,
        user_message: str,
    ) -> None:
        self._profile_service.observe(
            user_message
        )


class ProfileContextProvider:
    def __init__(
        self,
        profile_service: ProfileService,
    ):
        self._profile_service = (
            profile_service
        )

    def build_context(
        self,
        user_message: str,
    ) -> str:
        del user_message

        return (
            self._profile_service
            .build_context()
        )