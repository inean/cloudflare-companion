# Builder image
FROM debian:bookworm-slim AS builder

LABEL maintainer="inean <inean.es+contact@gmail.com>"

# hadolint ignore=DL3008
RUN <<EOF
    apt-get update
    apt-get install -y --no-install-recommends ca-certificates curl
EOF

# Download the latest installer
ADD https://astral.sh/uv/install.sh uv-installer.sh

# Run the installer then remove it
RUN sh uv-installer.sh && rm uv-installer.sh

# Devcontainer image
FROM mcr.microsoft.com/vscode/devcontainers/base:bookworm

# Set uv
ENV UV_HOME="/opt/.cargo/bin"
ENV PATH="$UV_HOME/:$PATH"
COPY --from=builder /root/.cargo/bin/uv $UV_HOME/uv

# Configure uv behavior
ENV PYTHONUNBUFFERED=True
ENV UV_LINK_MODE=copy

# Set workdir
WORKDIR /opt
# Define version of python interpreter to use
COPY ./.python-version ./
# Pin and install python interpreter
RUN uv python pin "$(cat .python-version)"

# let vscode user to use uv
RUN chown -R vscode $UV_HOME
