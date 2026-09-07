def render_task_journal(state):
    getter = getattr(state, "get_journal", None)
    if not callable(getter):
        return "GÖREV GÜNLÜĞÜ\nKalıcı task günlüğü bu sürümde etkin değil."
    entries = getter()
    lines = ["GÖREV GÜNLÜĞÜ", f"Kayıt: {len(entries)}"]
    for item in entries[-20:]:
        detail = " ".join(value for value in (item.task_id, item.status, item.note) if value)
        lines.append(f"- #{item.sequence} {item.event}" + (f": {detail}" if detail else ""))
    checkpoint_path = getattr(state, "checkpoint_path", None)
    if checkpoint_path is not None:
        lines.append(f"Checkpoint: {checkpoint_path}")
    checkpoint_schema = getattr(state, "checkpoint_schema", None)
    if checkpoint_schema:
        lines.append(f"Checkpoint şeması: {checkpoint_schema}")
    migrated_from = getattr(state, "checkpoint_migrated_from", None)
    if migrated_from is not None:
        target = checkpoint_schema.rpartition("/v")[2] if checkpoint_schema else "?"
        lines.append(f"Son yükleme: V{migrated_from} → V{target} migration tamamlandı.")
    return "\n".join(lines)
