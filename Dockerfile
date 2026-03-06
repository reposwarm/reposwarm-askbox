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
RUN mkdir -p /output

ENTRYPOINT ["python3", "-m", "src.agent"]
