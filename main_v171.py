from main_v170 import build_application


if __name__ == "__main__":
    application = build_application(
        application_version="V0.17.1",
        startup_message=(
            "Börü V0.17.1 hazır. Proje dosyası listeleme doğruluğu, "
            "Architect dosya kapsamı koruması ve Python geçici dosya "
            "filtreleri aktif."
        ),
    )
    application.mainloop()
