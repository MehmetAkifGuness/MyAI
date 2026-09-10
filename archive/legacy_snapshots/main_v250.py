from main_v170 import build_application


if __name__ == "__main__":
    application = build_application(
        application_version="V0.25",
        startup_message=(
            "Börü V0.25 hazır. Knowledge/RAG; güvenli yerel belge indeksi, hibrit "
            "arama ve kaynaklı yanıt üretimiyle aktif."
        ),
        structured_timeout_seconds=180,
        structured_num_predict=2048,
        architect_max_attempts=1,
        architect_fast_scoped_plans=True,
        coding_agent_enabled=True,
        test_agent_enabled=True,
        security_agent_enabled=True,
        code_review_agent_enabled=True,
        orchestrator_enabled=True,
        task_system_enabled=True,
        project_memory_enabled=True,
        knowledge_rag_enabled=True,
        project_edit_max_attempts=1,
    )
    application.mainloop()
