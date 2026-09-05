from main_v170 import build_application


if __name__ == "__main__":
    application = build_application(
        application_version="V0.17.2.2",
        startup_message=(
            "Börü V0.17.2.2 hazır. Açık dosya kapsamlı Architect planları "
            "anlık kaynak analizi ve temiz bölüm biçimiyle aktif."
        ),
        structured_timeout_seconds=90,
        structured_num_predict=384,
        architect_max_attempts=1,
        architect_fast_scoped_plans=True,
    )
    application.mainloop()
