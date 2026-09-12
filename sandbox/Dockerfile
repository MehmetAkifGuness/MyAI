FROM python:3.13-slim

# Güvenlik ve bytecode yalıtımı
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

# Temel bağımlılıklar ve apt temizliği
RUN apt-get update && apt-get install -y --no-install-recommends tk git && rm -rf /var/lib/apt/lists/*

# İzinli test ve doğrulama araçları
RUN pip install --no-cache-dir customtkinter ollama pytest ruff mypy

# İzolasyon dizini ve yetkisiz (unprivileged) kullanıcı yapılandırması
WORKDIR /workspace
RUN mkdir -p /workspace && chown -R 65534:65534 /workspace && chmod 755 /workspace

USER 65534:65534
ENTRYPOINT ["python"]
