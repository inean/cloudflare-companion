# Global args
ARG PYTHON_VERSION=3.11
ARG APP_PATH=/app
ARG VIRTUAL_ENV_PATH=.venv

# Builder stage
FROM ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-bookworm-slim AS builder

# Re-declare the ARG to use it in this stage
ARG APP_PATH
ARG VIRTUAL_ENV_PATH

# hadolint ignore=DL3008
RUN <<EOF
    apt-get update
    apt-get install --no-install-recommends -y git
EOF

# Set the working directory:
WORKDIR ${APP_PATH}

# Change ownership of the application directory to the non-root user
RUN chown -R nobody ${APP_PATH}

# Set uv environment variables
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy


# Install the application dependencies and build .venv:
# for rootless configurations like podman, add 'z' or relabel=shared
# to circumvent the SELinux context
#
# See https://github.com/hadolint/language-docker/issues/95 for hadolint support
RUN --mount=type=cache,target=/root/.cache/uv                         \
    --mount=type=bind,source=uv.lock,target=uv.lock,ro                \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml,ro  \
    uv sync --frozen --no-install-project --no-dev

# Copy the application source code:
COPY src .

# Final stage
FROM python:${PYTHON_VERSION}-slim as target

# Redeclare args
ARG APP_PATH
ARG VIRTUAL_ENV_PATH

# Image args
ARG REGISTRY="ghcr.io"
ARG REPOSITORY="inean/dns-synchub"

# Set labels for the image
LABEL url="https://github.com/${REPOSITORY}/"
LABEL image="${REGISTRY}/${REPOSITORY}"
LABEL maintainer="Carlos Martín (github.com/inean)"

# Set the working directory:
WORKDIR ${APP_PATH}

# Place executables in the environment at the front of the path
ENV PATH="${APP_PATH}/${VIRTUAL_ENV_PATH}/bin:$PATH"

# Copy dependencies and source code from the builder stage
COPY --from=builder ${APP_PATH} ${APP_PATH}

# Run the application:
ENTRYPOINT ["python", "-m", "dns_synchub"]

# Use CMD to pass arguments to the application
CMD ["--version"]
