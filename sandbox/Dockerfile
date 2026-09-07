FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends tk git && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir customtkinter ollama pytest ruff mypy
WORKDIR /workspace
USER 65534:65534
ENTRYPOINT ["python"]
