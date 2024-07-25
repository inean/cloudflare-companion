# Builder image
FROM debian:bookworm-slim AS builder

# hadolint ignore=DL3008
RUN <<EOF
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl
EOF

# Install rye
ENV RYE_HOME="/opt/rye"
ENV PATH="$RYE_HOME/shims:$PATH"

SHELL [ "/bin/bash", "-o", "pipefail", "-c" ]
RUN curl -sSf https://rye.astral.sh/get | RYE_INSTALL_OPTION="--yes" bash \
    && rye config --set-bool behavior.global-python=true \
    && rye config --set-bool behavior.use-uv=true

# Initialize rye
WORKDIR /opt

COPY ./.python-version \
    ./pyproject.toml  \
    ./requirements*   \
    ./

RUN <<EOF
    rye pin "$(cat .python-version)"
    rye sync
EOF

# Devcontainer image
FROM mcr.microsoft.com/vscode/devcontainers/base:bookworm
COPY --from=builder /opt/rye /opt/rye

ENV RYE_HOME="/opt/rye"
ENV PATH="$RYE_HOME/shims:$PATH"
ENV PYTHONUNBUFFERED=True

RUN <<EOF
    rye config --set-bool behavior.global-python=true
    rye config --set-bool behavior.use-uv=true
EOF

RUN chown -R vscode $RYE_HOME
