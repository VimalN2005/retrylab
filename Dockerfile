# syntax=docker/dockerfile:1
# RetryLab Chaos Sidecar: Zero-Code Containerized Reliability Proxy
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy packaging specifications
COPY pyproject.toml MANIFEST.in README.md LICENSE ./
COPY retrylab ./retrylab

# Build wheel package
RUN pip install --no-cache-dir build && \
    python -m build --wheel

# Final minimal production runtime stage
FROM python:3.12-slim AS runner

WORKDIR /app

# Create non-root system user and group for security
RUN groupadd -g 10001 retrylab && \
    useradd -u 10001 -g retrylab -m -s /bin/bash retrylab

# Copy and install built wheel from builder stage
COPY --from=builder /app/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && \
    rm -rf /tmp/*.whl

# Create scenarios directory
RUN mkdir -p /scenarios && chown -R retrylab:retrylab /scenarios /app

USER retrylab

# Standard sidecar interception and health probe port
EXPOSE 8080

# Built-in container healthcheck querying the sidecar health probe
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/_retrylab/health', timeout=2)" || exit 1

ENTRYPOINT ["retrylab", "sidecar"]
CMD ["--host", "0.0.0.0", "--port", "8080"]
