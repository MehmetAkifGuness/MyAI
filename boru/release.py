"""Single, shared feature configuration for the final release milestones."""


def build_release(version: str = "V2.1"):
    from main_v170 import build_application

    if version not in {"V0.27", "V0.28", "V0.29", "V1.0", "V1.1", "V1.2", "V1.3", "V1.4", "V1.5", "V1.6", "V1.7", "V1.8", "V1.9", "V2.0", "V2.1"}:
        raise ValueError("Desteklenmeyen sürüm.")
    evaluation = version != "V0.27"
    improvement = version in {"V0.29", "V1.0", "V1.1", "V1.2", "V1.3", "V1.4", "V1.5", "V1.6", "V1.7", "V1.8", "V1.9", "V2.0", "V2.1"}
    general_agent = version in {"V1.1", "V1.2", "V1.3", "V1.4", "V1.5", "V1.6", "V1.7", "V1.8", "V1.9", "V2.0", "V2.1"}
    deep_code_index = version in {"V1.2", "V1.3", "V1.4", "V1.5", "V1.6", "V1.7", "V1.8", "V1.9", "V2.0", "V2.1"}
    natural_change = version in {"V1.3", "V1.4", "V1.5", "V1.6", "V1.7", "V1.8", "V1.9", "V2.0", "V2.1"}
    goal_driven_change = version in {"V1.4", "V1.5", "V1.6", "V1.7", "V1.8", "V1.9", "V2.0", "V2.1"}
    impact_analysis = version in {"V1.5", "V1.6", "V1.7", "V1.8", "V1.9", "V2.0", "V2.1"}
    runtime_test_agent = version in {"V1.6", "V1.7", "V1.8", "V1.9", "V2.0", "V2.1"}
    runtime_repair = version in {"V1.7", "V1.8", "V1.9", "V2.0", "V2.1"}
    batch_runtime_repair = version in {"V1.8", "V1.9", "V2.0", "V2.1"}
    planned_task_execution = version in {"V1.9", "V2.0", "V2.1"}
    persistent_task_checkpoint = version in {"V2.0", "V2.1"}
    source_drift_detection = version == "V2.1"
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
        project_edit_max_attempts=2 if goal_driven_change else 1,
    )
