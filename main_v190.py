from main_v170 import build_application


if __name__ == "__main__":
    application = build_application(
        application_version="V0.19",
        startup_message=(
            "Börü V0.19 hazır. Test Agent; ilişkili test keşfi, güvenli hedefli "
            "çalıştırma, hata analizi ve Coding Agent sonrası regresyon kontrolüyle aktif."
        ),
        structured_timeout_seconds=180,
        structured_num_predict=2048,
        architect_max_attempts=1,
        architect_fast_scoped_plans=True,
        coding_agent_enabled=True,
        test_agent_enabled=True,
        project_edit_max_attempts=1,
    )
    application.mainloop()
