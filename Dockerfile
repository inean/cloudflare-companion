# Global args
ARG PYTHON_VERSION=3.11
ARG APP_PATH=/app
ARG VIRTUAL_ENV_PATH=.venv

# Builder stage
FROM python:${PYTHON_VERSION}-slim AS builder

# Re-declare the ARG to use it in this stage
ARG APP_PATH
ARG VIRTUAL_ENV_PATH

# hadolint ignore=DL3008
RUN <<EOF
    apt-get update
    apt-get install --no-install-recommends -y git
EOF

# hadolint ignore=DL3013
RUN pip install --no-cache-dir uv

# Set the working directory:
WORKDIR ${APP_PATH}

# Copy and install dependencies using uv:
COPY uv.lock .
RUN uv sync --locked --link-mode copy --no-cache --compile-bytecode --no-dev --all-extras

# Set a Virtual env
ENV PATH="${APP_PATH}/${VIRTUAL_ENV_PATH}/bin:$PATH"

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

# Ensure venv is used
ENV PATH="${APP_PATH}/${VIRTUAL_ENV_PATH}/bin:$PATH"

# Copy dependencies and source code from the builder stage
COPY --from=builder ${APP_PATH} ${APP_PATH}

# Run the application:
ENTRYPOINT ["python", "-m", "dns_synchub"]

# Use CMD to pass arguments to the application
CMD ["--version"]
