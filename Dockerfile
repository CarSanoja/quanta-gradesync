FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --gid 10001 appgroup \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin appuser

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN mkdir -p /tmp/autocurricula && chown appuser:appgroup /tmp/autocurricula

USER appuser

ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn autocurricula.api.main:app --host 0.0.0.0 --port ${PORT} --loop uvloop --http httptools"]
