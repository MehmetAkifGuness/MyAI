import re

from boru.tasks.models import TaskAction, TaskCommand


class RuleBasedTaskCommandParser:
    _PLAN = re.compile(
        r"^\s*(?:görev|task)\s+planla\s*:\s*(?P<objective>.+?)\s*$",
        re.IGNORECASE | re.DOTALL,
    )
    _STATUS = re.compile(
        r"^\s*(?:görev|task|plan)\s+durumu\s*[.!?]?\s*$",
        re.IGNORECASE,
    )
    _RUN = re.compile(
        r"^\s*task\s+(?:çalıştır|başlat)\s*:\s*(?P<task_id>TASK-[1-9]\d*)\s*$",
        re.IGNORECASE,
    )
    _RESET = re.compile(
        r"^\s*task\s+(?:sıfırla|yeniden\s+aç)\s*:\s*"
        r"(?P<task_id>TASK-[1-9]\d*)\s*$",
        re.IGNORECASE,
    )
    _COMPLETE = re.compile(
        r"^\s*task\s+(?:tamamla|kabul\s+et)\s*:\s*"
        r"(?P<task_id>TASK-[1-9]\d*)\s*$",
        re.IGNORECASE,
    )
    _INTENT = re.compile(
        r"^\s*(?:(?:görev|task)\s+(?:planla|durumu)|plan\s+durumu|"
        r"task\s+(?:çalıştır|başlat|sıfırla|yeniden\s+aç|tamamla|kabul\s+et))\b",
        re.IGNORECASE,
    )

    def __init__(self, max_objective_characters: int = 4000) -> None:
        if max_objective_characters < 1:
            raise ValueError("Task plan hedef sınırı pozitif olmalıdır.")
        self._max_objective_characters = max_objective_characters

    def parse(self, user_message: str) -> TaskCommand | None:
        match = self._PLAN.fullmatch(user_message)
        if match is not None:
            objective = match.group("objective").strip()
            if len(objective) > self._max_objective_characters:
                raise ValueError(
                    "Plan hedefi en fazla "
                    f"{self._max_objective_characters} karakter olabilir."
                )
            return TaskCommand(TaskAction.PLAN, objective)
        if self._STATUS.fullmatch(user_message):
            return TaskCommand(TaskAction.STATUS)
        match = self._RUN.fullmatch(user_message)
        if match is not None:
            return TaskCommand(TaskAction.RUN, match.group("task_id").upper())
        match = self._RESET.fullmatch(user_message)
        if match is not None:
            return TaskCommand(TaskAction.RESET, match.group("task_id").upper())
        match = self._COMPLETE.fullmatch(user_message)
        if match is not None:
            return TaskCommand(TaskAction.COMPLETE, match.group("task_id").upper())
        return None

    def is_task_intent(self, user_message: str) -> bool:
        return self._INTENT.search(user_message) is not None
