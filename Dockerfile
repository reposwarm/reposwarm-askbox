FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY src/ src/

ENV OUTPUT_DIR=/output
ENV IS_SANDBOX=1
ENV ASKBOX_PORT=8082
RUN mkdir -p /output

EXPOSE 8082

# Default: HTTP server mode. Override with: docker run ... python3 -m src.agent --question "..."
ENTRYPOINT ["python3", "-m", "src.server"]
