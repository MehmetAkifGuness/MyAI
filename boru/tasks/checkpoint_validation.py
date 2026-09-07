def validate_payload_fields(document):
    """Reject unknown nested fields before a migration could discard them."""
    plan = document.get("plan")
    if plan is not None:
        _fields(plan, {"objective", "summary", "tasks"})
        tasks = plan.get("tasks")
        if not isinstance(tasks, list):
            raise ValueError("Checkpoint task listesi geçersiz.")
        for task in tasks:
            _fields(task, {"task_id", "title", "description", "files", "dependencies", "status", "note"})
    for name, allowed in (
        ("journal", {"sequence", "event", "task_id", "status", "note"}),
        ("fingerprints", {"path", "sha256"}),
    ):
        values = document.get(name, [])
        if not isinstance(values, list):
            raise ValueError(f"Checkpoint {name} listesi geçersiz.")
        for value in values:
            _fields(value, allowed)


def _fields(value, allowed):
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError("Checkpoint beklenmeyen iç alan içeriyor; veri kaybını önlemek için durduruldu.")
