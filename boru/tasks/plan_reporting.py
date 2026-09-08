from boru.tasks.models import TaskStatus


def render_plan(plan, header, checkpoint_path=None):
    storage = (f"kalıcı checkpoint ({checkpoint_path})" if checkpoint_path is not None
               else "yalnızca bu uygulama oturumu")
    completed = sum(item.status is TaskStatus.COMPLETED for item in plan.tasks)
    lines = [header, f"Hedef: {plan.objective}", f"Özet: {plan.summary}",
             f"Saklama: {storage}", f"İlerleme: {completed}/{len(plan.tasks)} tamamlandı"]
    for item in plan.tasks:
        lines.extend(("", f"- {item.task_id} [{item.status.value}] {item.title}",
                      f"  {item.description}",
                      "  Dosyalar: " + (", ".join(item.files) or "belirtilmedi"),
                      "  Bağımlılık: " + (", ".join(item.dependencies) or "yok")))
        if item.note:
            lines.append(f"  Not: {item.note}")
    return "\n".join(lines)
