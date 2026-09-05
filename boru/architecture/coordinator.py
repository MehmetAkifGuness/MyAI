from boru.architecture.contracts import ArchitecturePlanner, ArchitectureRequestParser
from boru.architecture.models import ArchitecturePlan


class ArchitectCoordinator:
    _USAGE = "Mimari plan biçimi: 'mimari planla: yapılacak görev'."

    def __init__(self, parser: ArchitectureRequestParser, planner: ArchitecturePlanner) -> None:
        self._parser = parser
        self._planner = planner

    def resolve(self, user_message: str) -> str | None:
        try:
            request = self._parser.parse(user_message)
        except ValueError as error:
            return f"Mimari plan isteği reddedildi: {error} {self._USAGE}"
        if request is None:
            return self._USAGE if self._parser.is_architecture_intent(user_message) else None
        try:
            plan = self._planner.plan(request)
        except Exception as error:
            return f"Mimari plan hazırlanamadı: {error}"
        return self._render(plan)

    @staticmethod
    def _render(plan: ArchitecturePlan) -> str:
        sections = [
            "MİMARİ PLAN",
            f"Özet: {plan.summary}\n"
            "Mevcut dosyalar: " + (", ".join(plan.existing_files) or "yok") + "\n"
            "Yeni dosyalar: " + (", ".join(plan.new_files) or "yok"),
        ]
        steps = []
        for index, step in enumerate(plan.steps, start=1):
            files = f" [{', '.join(step.files)}]" if step.files else ""
            steps.append(f"{index}. {step.title}{files}\n   {step.description}")
        sections.append("Adımlar:\n\n" + "\n\n".join(steps))
        sections.append("Riskler:\n" + ArchitectCoordinator._render_items(plan.risks))
        sections.append("Test stratejisi:\n" + ArchitectCoordinator._render_items(plan.tests))
        sections.append("Mimari notlar:\n" + ArchitectCoordinator._render_items(plan.notes))
        sections.append("Salt-okunur analiz tamamlandı; hiçbir dosya değiştirilmedi.")
        return "\n\n".join(sections)

    @staticmethod
    def _render_items(items: tuple[str, ...]) -> str:
        return "\n".join(f"- {item}" for item in items) if items else "- yok"
