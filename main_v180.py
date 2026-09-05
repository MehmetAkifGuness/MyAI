from main_v170 import build_application


if __name__ == "__main__":
    application = build_application(
        application_version="V0.18",
        startup_message=(
            "Börü V0.18 hazır. Coding Agent; Architect kapsamı, grounded diff, "
            "açık onay, SHA-256 kontrolü, transaction ve rollback ile aktif."
        ),
        structured_timeout_seconds=180,
        structured_num_predict=2048,
        architect_max_attempts=1,
        architect_fast_scoped_plans=True,
        coding_agent_enabled=True,
        project_edit_max_attempts=1,
    )
    application.mainloop()
