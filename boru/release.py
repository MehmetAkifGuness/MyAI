"""Single, shared feature configuration for the final release milestones."""


def build_release(version: str = "V1.8"):
    from main_v170 import build_application

    if version not in {"V0.27", "V0.28", "V0.29", "V1.0", "V1.1", "V1.2", "V1.3", "V1.4", "V1.5", "V1.6", "V1.7", "V1.8"}:
        raise ValueError("Desteklenmeyen sürüm.")
    evaluation = version != "V0.27"
    improvement = version in {"V0.29", "V1.0", "V1.1", "V1.2", "V1.3", "V1.4", "V1.5", "V1.6", "V1.7", "V1.8"}
    general_agent = version in {"V1.1", "V1.2", "V1.3", "V1.4", "V1.5", "V1.6", "V1.7", "V1.8"}
    deep_code_index = version in {"V1.2", "V1.3", "V1.4", "V1.5", "V1.6", "V1.7", "V1.8"}
    natural_change = version in {"V1.3", "V1.4", "V1.5", "V1.6", "V1.7", "V1.8"}
    goal_driven_change = version in {"V1.4", "V1.5", "V1.6", "V1.7", "V1.8"}
    impact_analysis = version in {"V1.5", "V1.6", "V1.7", "V1.8"}
    runtime_test_agent = version in {"V1.6", "V1.7", "V1.8"}
    runtime_repair = version in {"V1.7", "V1.8"}
    batch_runtime_repair = version == "V1.8"
    features = "Docker sandbox"
    if evaluation:
        features += ", kanıta dayalı öz değerlendirme"
    if improvement:
        features += ", onaylı ve geri alınabilir iyileştirme"
    if general_agent:
        features += ", kanıtlı genel ajan ve güvenli kod indeksi"
    if deep_code_index:
        features += ", import/çağrı ilişkileri ve çoklu dosya kanıtı"
    if natural_change:
        features += ", doğal dilden onaylı değişiklik ve doğrulama döngüsü"
    if goal_driven_change:
        features += ", hedef odaklı hata teşhisi ve ilişkili dosya kapsamı"
    if impact_analysis:
        features += ", ters bağımlılık ve etkilenen test analizi"
    if runtime_test_agent:
        features += ", genel ajan için hedefli sandbox test kanıtı"
    if runtime_repair:
        features += ", başarısız testten onaylı düzeltme ve otomatik yeniden test"
    if batch_runtime_repair:
        features += ", çoklu test kök neden gruplama ve sınırlandırılmış çoklu dosya onarımı"
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
        project_edit_max_attempts=2 if goal_driven_change else 1,
    )
