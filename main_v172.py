from main_v170 import build_application


if __name__ == "__main__":
    application = build_application(
        application_version="V0.17.2",
        startup_message=(
            "Börü V0.17.2 hazır. Architect kaynak sembolü doğrulaması, "
            "sorumluluk sınırı yönlendirmesi ve temiz adım biçimi aktif."
        ),
    )
    application.mainloop()
