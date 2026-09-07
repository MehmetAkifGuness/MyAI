"""Single, shared feature configuration for the final release milestones."""


_RELEASES = (
    "V0.27", "V0.28", "V0.29", "V1.0", "V1.1", "V1.2", "V1.3", "V1.4",
    "V1.5", "V1.6", "V1.7", "V1.8", "V1.9", "V2.0", "V2.1", "V2.2",
    "V2.3", "V2.4", "V2.5", "V2.6", "V2.7", "V2.8", "V2.9", "V3.0",
)


def _enabled_from(version: str, milestone: str) -> bool:
    return _RELEASES.index(version) >= _RELEASES.index(milestone)


def build_release(version: str = "V3.0"):
    from main_v170 import build_application

    if version not in _RELEASES:
        raise ValueError("Desteklenmeyen sürüm.")
    evaluation = _enabled_from(version, "V0.28")
    improvement = _enabled_from(version, "V0.29")
    general_agent = _enabled_from(version, "V1.1")
    deep_code_index = _enabled_from(version, "V1.2")
    natural_change = _enabled_from(version, "V1.3")
    goal_driven_change = _enabled_from(version, "V1.4")
    impact_analysis = _enabled_from(version, "V1.5")
    runtime_test_agent = _enabled_from(version, "V1.6")
    runtime_repair = _enabled_from(version, "V1.7")
    batch_runtime_repair = _enabled_from(version, "V1.8")
    planned_task_execution = _enabled_from(version, "V1.9")
    persistent_task_checkpoint = _enabled_from(version, "V2.0")
    source_drift_detection = _enabled_from(version, "V2.1")
    checkpoint_migration = _enabled_from(version, "V2.2")
    reliable_tasks = _enabled_from(version, "V2.3")
    sandbox_terminal = _enabled_from(version, "V3.0")
    optional_features = (
        ("kanıta dayalı öz değerlendirme", evaluation),
        ("onaylı ve geri alınabilir iyileştirme", improvement),
        ("kanıtlı genel ajan ve güvenli kod indeksi", general_agent),
        ("import/çağrı ilişkileri ve çoklu dosya kanıtı", deep_code_index),
        ("doğal dilden onaylı değişiklik ve doğrulama döngüsü", natural_change),
        ("hedef odaklı hata teşhisi ve ilişkili dosya kapsamı", goal_driven_change),
        ("ters bağımlılık ve etkilenen test analizi", impact_analysis),
        ("genel ajan için hedefli sandbox test kanıtı", runtime_test_agent),
        ("başarısız testten onaylı düzeltme ve otomatik yeniden test", runtime_repair),
        (
            "çoklu test kök neden gruplama ve sınırlandırılmış çoklu dosya onarımı",
            batch_runtime_repair,
        ),
        ("bağımlılık sıralı plan yürütme ve adım bazlı doğrulama", planned_task_execution),
        ("kalıcı task checkpoint, güvenli yeniden başlatma ve işlem günlüğü", persistent_task_checkpoint),
        ("SHA-256 kaynak drift algılama ve eski plan durdurma", source_drift_detection),
        ("checkpoint şema sürümleme ve doğrulanmış otomatik migration", checkpoint_migration),
        ("checkpoint yedeği, onaylı kurtarma, proje kilidi, sınırlı yeniden deneme ve görev arşivi", reliable_tasks),
        ("Docker içinde izinli terminal komutları ve ortam raporu", sandbox_terminal),
    )
    features = ", ".join(
        ("Docker sandbox", *(name for name, enabled in optional_features if enabled))
    )
    return build_application(
        application_version=version,
        startup_message=f"Börü {version} hazır. {features} aktif. Testler için Docker Linux motoru gereklidir.",
        structured_timeout_seconds=180, structured_num_predict=2048,
        architect_max_attempts=1, architect_fast_scoped_plans=True,
        coding_agent_enabled=True, test_agent_enabled=True, security_agent_enabled=True,
        code_review_agent_enabled=True, orchestrator_enabled=True, task_system_enabled=True,
        project_memory_enabled=True, knowledge_rag_enabled=True, external_tools_enabled=True,
        sandbox_enabled=True, evaluation_enabled=evaluation, improvement_enabled=improvement,
        general_agent_enabled=general_agent,
        deep_code_index_enabled=deep_code_index,
        natural_change_enabled=natural_change,
        goal_driven_change_enabled=goal_driven_change,
        impact_analysis_enabled=impact_analysis,
        runtime_test_agent_enabled=runtime_test_agent,
        runtime_repair_enabled=runtime_repair,
        batch_runtime_repair_enabled=batch_runtime_repair,
        planned_task_execution_enabled=planned_task_execution,
        persistent_task_checkpoint_enabled=persistent_task_checkpoint,
        source_drift_detection_enabled=source_drift_detection,
        reliable_tasks_enabled=reliable_tasks,
        sandbox_terminal_enabled=sandbox_terminal,
        project_edit_max_attempts=2 if goal_driven_change else 1,
    )
