# Builder image
FROM debian:bookworm-slim AS builder

# hadolint ignore=DL3008
RUN <<EOF
    apt-get update
    apt-get install -y --no-install-recommends ca-certificates curl
EOF

# Install and initialize rye
ENV RYE_HOME="/opt/rye"
ENV PATH="$RYE_HOME/shims:$PATH"

# hadolint ignore=DL4006
RUN <<EOF
    curl -sSf https://rye.astral.sh/get | RYE_INSTALL_OPTION="--yes" bash
    rye config --set-bool behavior.global-python=true
    rye config --set-bool behavior.use-uv=true
EOF

# Copy project
WORKDIR /opt

# Find pinned python version on current project and download it
COPY ./.python-version ./
RUN rye pin "$(cat .python-version)"

# Devcontainer image
FROM mcr.microsoft.com/vscode/devcontainers/base:bookworm
COPY --from=builder /opt/rye /opt/rye

ENV RYE_HOME="/opt/rye"
ENV PATH="$RYE_HOME/shims:$PATH"
ENV PYTHONUNBUFFERED=True

# Use rye as the default python and uv as default package manager
RUN <<EOF
    rye config --set-bool behavior.global-python=true
    rye config --set-bool behavior.use-uv=true
EOF

RUN chown -R vscode $RYE_HOME
