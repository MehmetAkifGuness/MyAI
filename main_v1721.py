from main_v170 import build_application


if __name__ == "__main__":
    application = build_application(
        application_version="V0.17.2.1",
        startup_message=(
            "Börü V0.17.2.1 hazır. Architect kısa structured üretim, "
            "90 saniyelik süre sınırı ve kaynak-temelli güvenli fallback ile aktif."
        ),
        structured_timeout_seconds=90,
        structured_num_predict=384,
        architect_max_attempts=1,
    )
    application.mainloop()
