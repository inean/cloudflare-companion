# Define the build argument with no default value
ARG PYTHON_VERSION=3.10

# Builder stage
FROM python:${PYTHON_VERSION}-slim AS builder

# hadolint ignore=DL3008
RUN <<EOF
    apt-get update
    apt-get install --no-install-recommends -y git
EOF

# Set the working directory:
WORKDIR /app

# Copy and install dependencies:
COPY requirements.lock ./
RUN PYTHONDONTWRITEBYTECODE=1 pip install --no-cache-dir -r requirements.lock

# Copy the application source code:
COPY src .

# Final stage
FROM python:${PYTHON_VERSION}-slim

# Define the build argument with a default value
ARG REGISTRY="ghcr.io"
ARG REPOSITORY="inean/dns-synchub"

# Set labels for the image
LABEL url="https://github.com/${REPOSITORY}/"
LABEL image="${REGISTRY}/${REPOSITORY}"
LABEL maintainer="Carlos Martín (github.com/inean)"

# Set the working directory:
WORKDIR /app

# Copy dependencies and source code from the builder stage
COPY --from=builder /app /app

# Run the application:
ENTRYPOINT ["python", "-m", "dns_synchub"]

# Use CMD to pass arguments to the application
CMD ["--version"]
