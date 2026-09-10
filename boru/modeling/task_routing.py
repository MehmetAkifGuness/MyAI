from boru.modeling.structured import StructuredModelCascade


class TaskModelRouter:
    """Select the configured secondary model for complex tasks and repair feedback."""

    def __init__(self, model):
        self._model = model
        self.last_route = "primary"

    def for_task(self, objective: str, file_count: int = 1):
        complex_task = file_count > 1 or any(
            word in objective.casefold()
            for word in ("traceback", "onarım_kanıtı", "failed_candidate", "refactor")
        )
        if complex_task and isinstance(self._model, StructuredModelCascade):
            self.last_route = "fallback"
            return StructuredModelCascade(self._model.fallback, self._model.primary)
        self.last_route = "primary"
        return self._model

    def describe(self) -> str:
        primary = getattr(self._model, "primary", self._model)
        fallback = getattr(self._model, "fallback", None)
        return (
            "MODEL YÖNLENDİRME\n"
            f"Ana model: {getattr(primary, '_model_name', type(primary).__name__)}\n"
            f"Yedek model: {getattr(fallback, '_model_name', type(fallback).__name__) if fallback else 'tanımlı değil'}\n"
            f"Son seçim: {self.last_route}\n"
            "Çoklu dosya ve onarım istekleri varsa yapılandırılmış yedek modelle başlar."
        )


class RoutedProjectPreparer:
    def __init__(self, router, factory):
        self.router = router
        self.factory = factory

    def prepare_project_edit(self, request):
        model = self.router.for_task(request.instruction, len(request.existing_file_scope or ()))
        return self.factory(model).prepare_project_edit(request)
