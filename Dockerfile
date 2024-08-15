ARG VARIANT=3.10
FROM python:${VARIANT}-slim

LABEL url="https://github.com/inean/docker-traefik-cloudflare-companion/"
LABEL image="ghcr.io/inean/traefik-cloudflare-companion"
LABEL maintainer="Carlos Martín (github.com/inean)"

# Set a Virtual env if needed
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Install dependencies:
WORKDIR /app
COPY requirements.lock ./
RUN PYTHONDONTWRITEBYTECODE=1 pip install --no-cache-dir -r requirements.lock

COPY src .

# Run the application:
ENTRYPOINT ["/app/cloudflare_companion.py"]

# Use CMD to pass arguments to the application
CMD ["--version"]
