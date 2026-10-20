FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c

RUN python -m pip install --no-cache-dir \
    mypy==1.20.2 \
    pytest==9.1.1 \
    ruff==0.17.1

WORKDIR /workspace
