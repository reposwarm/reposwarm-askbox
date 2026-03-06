FROM node:22-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git python3 python3-pip python3-venv && \
    rm -rf /var/lib/apt/lists/*

# Claude Agent SDK requires the Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

WORKDIR /app

COPY pyproject.toml .
RUN python3 -m venv /app/.venv && \
    /app/.venv/bin/pip install --no-cache-dir .

COPY src/ src/

ENV PATH="/app/.venv/bin:$PATH"
ENV OUTPUT_DIR=/output
RUN mkdir -p /output

ENTRYPOINT ["python3", "-m", "src.agent"]
