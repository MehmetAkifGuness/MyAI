"""Single, shared feature configuration for the final release milestones."""


_RELEASES = (
    "V0.27", "V0.28", "V0.29", "V1.0", "V1.1", "V1.2", "V1.3", "V1.4",
    "V1.5", "V1.6", "V1.7", "V1.8", "V1.9", "V2.0", "V2.1", "V2.2",
    "V2.3", "V2.4", "V2.5", "V2.6", "V2.7", "V2.8", "V2.9", "V3.0",
    "V3.1", "V3.2", "V3.3", "V3.4", "V3.5", "V3.6", "V3.7", "V3.8",
    "V3.9", "V4.0",
    "V4.1", "V4.2", "V4.3", "V4.4", "V4.5", "V4.6", "V4.7", "V4.8",
    "V4.9", "V5.0", "V5.1", "V5.2", "V6.0", "V6.1", "V6.2", "V6.3",
    "V6.4", "V6.5", "V6.6", "V7.0", "V8.0", "V9.0", "V10.0", "V11.0", "V12.0", "V13.0",
)


_MILESTONES = {
    "evaluation": "V0.28", "improvement": "V0.29", "general_agent": "V1.1",
    "deep_code_index": "V1.2", "natural_change": "V1.3", "goal_driven_change": "V1.4",
    "impact_analysis": "V1.5", "runtime_test_agent": "V1.6", "runtime_repair": "V1.7",
    "batch_runtime_repair": "V1.8", "planned_task_execution": "V1.9",
    "persistent_task_checkpoint": "V2.0", "source_drift_detection": "V2.1",
    "checkpoint_migration": "V2.2", "reliable_tasks": "V2.3",
    "sandbox_terminal": "V3.0", "advanced_terminal": "V3.1",
    "autonomous_development": "V4.0",
    "staged_coding": "V6.3",
    "reliable_structured_calls": "V6.4",
    "relevant_context": "V6.5",
    "staged_feedback_repair": "V6.6",
    "agentic_benchmark": "V7.0",
    "benchmark_observability": "V8.0",
    "adaptive_model_routing": "V8.0",
    "repository_intelligence": "V9.0",
    "repository_workspace": "V10.0",
    "intelligent_task_intake": "V11.0",
    "deep_reasoning": "V12.0",
    "web_research": "V13.0",
    "conversation_quality": "V13.0",
}


def _release_flags(version: str) -> dict[str, bool | int]:
    position = _RELEASES.index(version)
    flags = {
        name: position >= _RELEASES.index(milestone)
        for name, milestone in _MILESTONES.items()
    }
    flags["terminal_feature_level"] = min(9, max(0, position - _RELEASES.index("V3.0")))
    flags["autonomy_feature_level"] = min(13, max(0, position - _RELEASES.index("V4.0")))
    return flags


def _feature_labels(flags: dict[str, bool | int]) -> tuple[tuple[str, bool], ...]:
    autonomy = int(flags["autonomy_feature_level"])
    return (
        ("kanıta dayalı öz değerlendirme", bool(flags["evaluation"])),
        ("onaylı ve geri alınabilir iyileştirme", bool(flags["improvement"])),
        ("kanıtlı genel ajan ve güvenli kod indeksi", bool(flags["general_agent"])),
        ("import/çağrı ilişkileri ve çoklu dosya kanıtı", bool(flags["deep_code_index"])),
        ("doğal dilden onaylı değişiklik ve doğrulama döngüsü", bool(flags["natural_change"])),
        ("hedef odaklı hata teşhisi ve ilişkili dosya kapsamı", bool(flags["goal_driven_change"])),
        ("ters bağımlılık ve etkilenen test analizi", bool(flags["impact_analysis"])),
        ("genel ajan için hedefli sandbox test kanıtı", bool(flags["runtime_test_agent"])),
        ("başarısız testten onaylı düzeltme ve yeniden test", bool(flags["runtime_repair"])),
        ("sınırlandırılmış çoklu dosya onarımı", bool(flags["batch_runtime_repair"])),
        ("bağımlılık sıralı plan yürütme", bool(flags["planned_task_execution"])),
        ("kalıcı task checkpoint ve işlem günlüğü", bool(flags["persistent_task_checkpoint"])),
        ("SHA-256 kaynak drift algılama", bool(flags["source_drift_detection"])),
        ("checkpoint şema migration", bool(flags["checkpoint_migration"])),
        ("yedek, proje kilidi, retry ve görev arşivi", bool(flags["reliable_tasks"])),
        ("Docker içinde izinli terminal", bool(flags["sandbox_terminal"])),
        ("çalışma dizini, kalite hattı ve terminal günlüğü", bool(flags["advanced_terminal"])),
        ("onaylı otonom geliştirme döngüsü", bool(flags["autonomous_development"])),
        ("yazım toleranslı otonom komutlar", autonomy >= 1),
        ("ayrı planlama ve başlatma", autonomy >= 3),
        ("duraklatma ve checkpoint sürdürme", autonomy >= 5),
        ("sınırlı task yeniden deneme", autonomy >= 6),
        ("hedefli kanıt doğrulaması", autonomy >= 7),
        ("birleşik görev özeti", autonomy >= 8),
        ("plan arşivi ve sınır raporu", autonomy >= 9),
        ("denetimli otonom geliştirme kontrol merkezi", autonomy >= 10),
        ("güncel task teşhisi ve kaynak/test kanıtı", autonomy >= 11),
        ("testleri koruyan onaylı task onarımı", autonomy >= 12),
        ("çok adımlı ilerleme ve sınırlı yeniden doğrulama", autonomy >= 13),
        ("ana dosyaya yazmadan önce geçici kopyada doğrulama", bool(flags["staged_coding"])),
        ("doğrulama geri bildirimli structured yeniden deneme", bool(flags["reliable_structured_calls"])),
        ("kod indeksli akıllı bağlam seçimi", bool(flags["relevant_context"])),
        ("sandbox testinden sınırlı onarım döngüsü", bool(flags["staged_feedback_repair"])),
        ("ölçülebilir model-test-onarım benchmarkı", bool(flags["agentic_benchmark"])),
        ("ilerleme, ETA ve iptal destekli benchmark", bool(flags["benchmark_observability"])),
        ("başarısız structured görevlerde yedek model yönlendirmesi", bool(flags["adaptive_model_routing"])),
        ("güvenli GitHub içe aktarma ve gerçek repo zekâsı", bool(flags["repository_intelligence"])),
        ("kalıcı ve izole repo çalışma alanı", bool(flags["repository_workspace"])),
        ("kanıtlı görev anlama ve hedefli netleştirme", bool(flags["intelligent_task_intake"])),
        ('kaynak okuyan araştırma döngüsü, görev bazlı model seçimi ve doğrulanmış deneyim', bool(flags['deep_reasoning'])),
        ('güvenli web arama, sayfa okuma ve kaynaklı web yanıtları', bool(flags['web_research'])),
        ('bağlamı takip eden gündelik sohbet ve yanıt kalite kontrolü', bool(flags['conversation_quality'])),
    )


def build_release(version: str = "V13.0"):
    from main_v170 import build_application

    if version not in _RELEASES:
        raise ValueError("Desteklenmeyen sürüm.")
    flags = _release_flags(version)
    features = ", ".join((
        "Docker sandbox",
        *(name for name, enabled in _feature_labels(flags) if enabled),
    ))
    return build_application(
        application_version=version,
        startup_message=(
            f"Börü {version} hazır. {features} aktif. "
            "Testler için Docker Linux motoru gereklidir."
        ),
        structured_timeout_seconds=180, structured_num_predict=2048,
        architect_max_attempts=2 if flags["adaptive_model_routing"] else 1,
        architect_fast_scoped_plans=True,
        coding_agent_enabled=True, test_agent_enabled=True, security_agent_enabled=True,
        code_review_agent_enabled=True, orchestrator_enabled=True, task_system_enabled=True,
        project_memory_enabled=True, knowledge_rag_enabled=True, external_tools_enabled=True,
        sandbox_enabled=True, evaluation_enabled=bool(flags["evaluation"]),
        improvement_enabled=bool(flags["improvement"]),
        general_agent_enabled=bool(flags["general_agent"]),
        deep_code_index_enabled=bool(flags["deep_code_index"]),
        natural_change_enabled=bool(flags["natural_change"]),
        goal_driven_change_enabled=bool(flags["goal_driven_change"]),
        impact_analysis_enabled=bool(flags["impact_analysis"]),
        runtime_test_agent_enabled=bool(flags["runtime_test_agent"]),
        runtime_repair_enabled=bool(flags["runtime_repair"]),
        batch_runtime_repair_enabled=bool(flags["batch_runtime_repair"]),
        planned_task_execution_enabled=bool(flags["planned_task_execution"]),
        persistent_task_checkpoint_enabled=bool(flags["persistent_task_checkpoint"]),
        source_drift_detection_enabled=bool(flags["source_drift_detection"]),
        reliable_tasks_enabled=bool(flags["reliable_tasks"]),
        sandbox_terminal_enabled=bool(flags["sandbox_terminal"]),
        autonomous_development_enabled=bool(flags["autonomous_development"]),
        autonomy_feature_level=int(flags["autonomy_feature_level"]),
        staged_coding_enabled=bool(flags["staged_coding"]),
        reliable_structured_calls_enabled=bool(flags["reliable_structured_calls"]),
        relevant_context_enabled=bool(flags["relevant_context"]),
        staged_feedback_repair_enabled=bool(flags["staged_feedback_repair"]),
        benchmark_chat_enabled=bool(flags["agentic_benchmark"]),
        adaptive_model_routing_enabled=bool(flags["adaptive_model_routing"]),
        repository_intelligence_enabled=bool(flags["repository_intelligence"]),
        repository_workspace_enabled=bool(flags["repository_workspace"]),
        intelligent_task_intake_enabled=bool(flags["intelligent_task_intake"]),
        deep_reasoning_enabled=bool(flags['deep_reasoning']),
        web_research_enabled=bool(flags['web_research']),
        conversation_quality_enabled=bool(flags['conversation_quality']),
        terminal_feature_level=int(flags["terminal_feature_level"]),
        project_edit_max_attempts=2 if flags["goal_driven_change"] else 1,
    )
