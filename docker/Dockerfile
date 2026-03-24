# Multi-stage build for production-hardened Python environment
# Stage 1: Builder
FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Gateway (API layer)
FROM python:3.11-slim-bookworm AS gateway

# Create non-root user
RUN groupadd -r eaas -g 1000 && \
    useradd -r -g eaas -u 1000 eaas-gateway

WORKDIR /app

# Copy only necessary artifacts from builder
COPY --from=builder /root/.local /home/eaas-gateway/.local
COPY --chown=eaas-gateway:eaas api_gateway/ ./api_gateway/
COPY --chown=eaas-gateway:eaas core_engine/ ./core_engine/

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set environment
ENV PATH=/home/eaas-gateway/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

USER eaas-gateway

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["python", "-m", "uvicorn", "api_gateway.main:app", "--host", "0.0.0.0", "--port", "8080"]

# Stage 3: Agent Runner (isolated execution environment)
FROM python:3.11-slim-bookworm AS agent-runner

# Create non-root agent user (different UID for isolation)
RUN groupadd -r eaas -g 1000 && \
    useradd -r -g eaas -u 1001 eaas-agent

WORKDIR /app

# Minimal dependencies for agents
COPY --from=builder /root/.local /home/eaas-agent/.local
COPY --chown=eaas-agent:eaas agent_runner/ ./agent_runner/

# Read-only filesystem setup
RUN mkdir -p /tmp /app/data && \
    chown -R eaas-agent:eaas /tmp /app/data

ENV PATH=/home/eaas-agent/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

USER eaas-agent

# No EXPOSE - agents have no network by default
ENTRYPOINT ["python", "-m", "agent_runner"]
