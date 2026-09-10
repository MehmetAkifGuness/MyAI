from main_v170 import build_application


if __name__ == "__main__":
    application = build_application(
        application_version="V0.26",
        startup_message=(
            "Börü V0.26 hazır. API ve Database araçları; HTTPS host politikası, "
            "onaylı yazma istekleri ve salt-okunur SQLite incelemeyle aktif."
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
        external_tools_enabled=True,
        project_edit_max_attempts=1,
    )
    application.mainloop()
