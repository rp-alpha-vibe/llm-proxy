FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus-multiproc

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

COPY config ./config

RUN mkdir -p /tmp/prometheus-multiproc

EXPOSE 8000

CMD ["python", "-m", "llm_proxy.main"]
