# [DNS SncHub](github.com/inean/dns-synchub)

[![GitHub Container Registry](https://img.shields.io/badge/GitHub%20Container%20Registry-available-brightgreen?style=flat-square&logo=github)](https://github.com/inean/dns-synchub/pkgs/container/dns-synchub)
[![CI](https://github.com/inean/dns-synchub/actions/workflows/containers.yml/badge.svg?style=flat-square)](https://github.com/inean/dns-synchub/actions/workflows/containers.yml)
[![codecov](https://codecov.io/github/inean/dns-synchub/graph/badge.svg?token=LHEA7AKBW0&style=flat-square)](https://codecov.io/github/inean/dns-synchub)
[![Known Vulnerabilities](https://snyk.io/test/github/inean/dns-synchub/main/badge.svg?style=flat-square)](https://snyk.io/test/github/inean/main/dns-synchub)
[![Mergify Status](https://img.shields.io/endpoint.svg?url=https://api.mergify.com/v1/badges/inean/dns-synchub&style=flat-square)](https://mergify.io)

## Overview

DNS Synchub is a containerized solution designed to automatically update DNS records for zone providers, currently supporting [Cloudflare](https://www.cloudflare.com/), upon container start.

This container's primary function is to expose services via a Cloudflare Tunnel, ensuring secure and reliable access. Leveraging Cloudflare's tunneling capabilities, it securely routes traffic to internal services without direct internet exposure.

It integrates with the [Traefik](https://github.com/traefik/traefik) reverse proxy, ensuring DNS records are synchronized with the container's lifecycle. This project simplifies DNS management in dynamic environments by automating DNS updates based on container status and Traefik routes.

This work is a rewrite of [docker-traefik-cloudflare-companion](https://github.com/tiredofit/docker-traefik-cloudflare-companion), maintained by [Dave Conroy](https://github.com/tiredofit/).

## Maintainer

- [Carlos Martín](https:/github.com/inean)

## Table of Contents

- [DNS SncHub](#dns-snchub)
  - [Overview](#overview)
  - [Maintainer](#maintainer)
  - [Table of Contents](#table-of-contents)
  - [Prerequisites and Assumptions](#prerequisites-and-assumptions)
  - [Installation](#installation)
    - [Build from Source](#build-from-source)
    - [Prebuilt Images](#prebuilt-images)
      - [Multi-Architecture Support](#multi-architecture-support)
  - [How it Works](#how-it-works)
    - [Discovery](#discovery)
      - [Configuring DNS Record Updates](#configuring-dns-record-updates)
    - [Filtering](#filtering)
      - [Pattern Matching](#pattern-matching)
        - [Include Patterns](#include-patterns)
        - [Exclude Patterns](#exclude-patterns)
      - [By Label (Docker Endpoint only)](#by-label-docker-endpoint-only)
  - [Configuration](#configuration)
    - [Requirements](#requirements)
      - [Access to Docker Socket](#access-to-docker-socket)
      - [Security Considerations](#security-considerations)
        - [Secrets](#secrets)
      - [Example Docker Compose Configuration](#example-docker-compose-configuration)
    - [Settings](#settings)
      - [General Settings](#general-settings)
      - [Discovery Settings](#discovery-settings)
      - [Docker](#docker)
        - [Docker Options](#docker-options)
        - [Filtering (Docker exclusively)](#filtering-docker-exclusively)
      - [Traefik](#traefik)
        - [Traefik Options](#traefik-options)
      - [Synchronization Settings](#synchronization-settings)
        - [Configuring Domain Options](#configuring-domain-options)
        - [Host Filtering Configuration](#host-filtering-configuration)
      - [Cloudflare](#cloudflare)
  - [Maintenance](#maintenance)
    - [Shell Access](#shell-access)
    - [Telemetry](#telemetry)
      - [Setup](#setup)
  - [Support](#support)
    - [Bug Reporting](#bug-reporting)
    - [Feature Requests](#feature-requests)
    - [Release Updates](#release-updates)
  - [License](#license)
  - [References](#references)

## Prerequisites and Assumptions

- Requires a [Scoped API key](https://developers.cloudflare.com/api/tokens/create) or a [Global API key](https://support.cloudflare.com/hc/en-us/articles/200167836-Managing-API-Tokens-and-Keys#12345680) from Cloudflare. The Scoped API key allows for more granular permissions, while the Global API key provides full access to your [Cloudflare](https://www.cloudflare.com/) account.

- Requires [Traefik](https://traefik.io/) v2.0 or later as a reverse proxy. Traefik is a modern HTTP reverse proxy and load balancer that simplifies deploying microservices.

- Supports only [Docker Engine](https://www.docker.com/products/docker-engine) or compatible (e.g., [Podman](https://podman.io/)). Docker Engine is the industry-leading container runtime, and Podman is a daemonless container engine for developing, managing, and running OCI Containers on your Linux system.

## Installation

### Build from Source

Clone this repository and build the container image using the following command:

```bash
docker build -t <imagename> .
```

### Prebuilt Images

Builds of the image are available on the [Github Container Registry](https://github.com/inean/dns-synchub/pkgs/container/dns-synchub)

```bash
docker pull ghcr.io/inean/dns-synchub:(imagetag)
```

The following image tags are available along with their tagged release based on what's written in the [Changelog](CHANGELOG.md):

| Container OS             | Tag       |
| ------------------------ | --------- |
| python-`<version>`-slim  | `:latest` |

The current Python version is specified in the `.python-version` file.

#### Multi-Architecture Support

Images are primarily tested on `arm64` architecture. Currently, the available architectures are `arm64` and `amd64`. Other variants, if available, are unsupported. To verify multi-architecture support for this image, use the command: `docker manifest inspect <image>:<tag>`.

## How it Works

Upon startup, the image scans containers for Traefik labels used to define routing rules. It filters out all labels except those containing `Host*` endpoints, extracts their content, and uses it to update [Cloudflare](https://www.cloudflare.com/) DNS records. For more information on Traefik routing rules, refer to the [Traefik Documentation](https://doc.traefik.io/traefik/routing/routers/).

### Discovery

`dns-synchub` supports two discovery modes: Docker and Traefik Polling. By default, only the Docker discovery mode is enabled. Once matching hosts are discovered, `dns-synchub` will add or update DNS records in Cloudflare to point to the configured `TARGET_DOMAIN`.

#### Configuring DNS Record Updates

A DNS record update requires the following parameters. These parameters have default values but can be customized on a per-domain basis:

| Parameter       | Description                                       | Required | Default Value |
|-----------------|---------------------------------------------------|----------|---------------|
| `NAME`          | The name of the domain to be updated.             | Yes      | N/A           |
| `TARGET_DOMAIN` | The target domain for the DNS record.             | Yes      | N/A           |
| `RC_TYPE`       | The type of DNS record (e.g., A, CNAME, etc.).    | No       | CNAME         |

To customize parameters for multiple domains, prefix the default parameters with `DOMAIN` followed by an index, separated by double underscores (`__`), following [Pydantic](https://pydantic-docs.helpmanual.io/) logic for setting.

```bash
# Default values
export RC_TYPE="CNAME"
export TARGET_DOMAIN="example.ltd"

# Domain-specific values
export DOMAIN__0__NAME="subdomain1.example.ltd"
export DOMAIN__0__RC_TYPE="A"
export DOMAIN__0__TARGET_DOMAIN="203.0.113.42"

export DOMAIN__1__NAME="subdomain2.example.ltd"
# Uses default RC_TYPE and TARGET_DOMAIN
```

\[!NOTE\]
In the example, if `dns-synchub` finds at least one service which exposes a Traefik rule with values set to `Host('subdomain1.example.ltd')` and `Host('subdomain2.example.ltd')`, it will update DNS records with the first one pointing an *A* record to `203.0.113.42` and the second one with a *CNAME* record redirecting to `example.ltd`.

\[!IMPORTANT\]
The index must start at **`0`**. In this case, the `NAME` environment variable will be ignored, and `TARGET_DOMAIN` will only be required if it is not specified for each domain.

### Filtering

Discovered hosts are evaluated against include and exclude patterns to determine their eligibility for synchronization with Cloudflare. By default, all discovered hosts are included. Exclude patterns take precedence over include patterns. These defaults can be modified by configuring the appropriate include and exclude patterns.

#### Pattern Matching

##### Include Patterns

Include patterns are specified using environment variables prefixed with `INCLUDED_HOST__`. Each variable should be suffixed with a sequential unique identifier starting from 0 (e.g., `INCLUDED_HOST__0`, `INCLUDED_HOST__1`). The value of each variable should be a regular expression that matches the desired hostnames. For example:

- `INCLUDED_HOST__0=.*-data\.foobar\.com`
- `INCLUDED_HOST__1=.*-api\.foobar\.com`

These regular expressions are used to determine if a host should be included in the synchronization process.

##### Exclude Patterns

Exclude patterns can be specified by defining one or more `EXCLUDED_HOST__` variables, each followed by a suffix which is a sequential unique identifier starting from 0 (e.g., `EXCLUDED_HOST__0`, `EXCLUDED_HOST__1`). The value of each variable should be a regular expression that matches the hostnames to be excluded. For example:

- `EXCLUDED_HOST__0=private-data\.foobar\.com`
- `EXCLUDED_HOST__1=.*-internal-api\.foobar\.com`

These regular expressions are used to determine if a host should be excluded from the synchronization process. Exclude patterns are applied after include patterns, ensuring that any host matching an exclude pattern is filtered out, even if it matches an include pattern.

#### By Label (Docker Endpoint only)

When both `DOCKER_FILTER_LABEL` and `DOCKER_FILTER_VALUE` are set, `dns-synchub` will only operate on containers that match these specified label-value pairs. This feature is particularly useful in environments where multiple instances of Traefik and `dns-synchub` are running on the same system or cluster. It allows for precise targeting of specific containers, ensuring that only those with the designated labels are affected.

For example:

```bash
DOCKER_CONSTRAINT_LABEL=traefik.constraint
DOCKER_CONSTRAINT_VALUE=proxy-public
```

In your serving container:

```yaml
services:
  nginx:
    image: inean/nginx:latest
    deploy:
      labels:
        - traefik.enable=true
        - traefik.http.routers.nginx.rule=Host(`nginx.example.com`)
        - ...
        - traefik.constraint=proxy-public
```

## Configuration

The quickest way to get started is using [docker-compose](https://docs.docker.com/compose/). To properly update zones on [Cloudflare](https://www.cloudflare.com/), the `dns-synchub` container may require special permissions to run. Specifically, it needs access to `/var/run/docker.sock`.

### Requirements

#### Access to Docker Socket

The container must have access to `/var/run/docker.sock` to interact with the Docker daemon and manage DNS updates based on container events.

#### Security Considerations

To use the leaked socket in the container, you need to run the container with the command-line option `--security-opt apparmor=unconfined`. This option disables SELinux security labeling, allowing the container to access the Docker socket.

##### Secrets

Sensitive information can be securely managed using Docker Secrets. To pass the Cloudflare Scoped Token to `dns-synchub`, follow these steps:

1. Create a Docker Secret named `cf_token` containing your Cloudflare Scoped API token.
1. Ensure the secret is accessible to the container.

Docker automatically makes the secret available to the container, allowing `dns-synchub` to securely access the token. By default, `dns-synchub` looks for secrets defined in the `/var/run` directory.

#### Example Docker Compose Configuration

```yaml
version: '3.8'
services:
  zone-updater:
    image: ghcr.io/inean/dns-synchub:latest
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    security_opt:
      - apparmor=unconfined
    secrets:
      - cf_token
    environment:
      - NAME=dubdomain1.example.ltd
      - TARGET_DOMAIN=intranet.example.ltd

secrets:
  cf_token:
    external: true
```

### Settings

`dns-synchub` relies on environment variables for configuration. These variables can be read from the system or provided via a `.env` file using the `--env-file` argument. The `.env` file should follow the `python-dotenv` syntax. Ensure that all required variables are set correctly to enable proper synchronization.

#### General Settings

| Parameter         | Description                                      | Type                       | Default         |
|-------------------|--------------------------------------------------|----------------------------|-----------------|
| `DRY_RUN`         | Perform a test run without making any changes.   | `BOOL`                     | `FALSE`         |
| `LOG_LEVEL`       | Logging level.                                   | `INFO, VERBOSE, DEBUG`     | `INFO`          |
| `LOG_TYPE`        | Log type.                                        | `CONSOLE, FILE, BOTH`      | `BOTH`          |
| `LOG_FILE`        | Absolute filepath for the log file               | `STR`                      | `/logs/tcc.log` |
| `REFRESH_ENTRIES` | If record exists, update entry with new values   | `BOOL`                     | `FALSE`         |

#### Discovery Settings

The current implementation supports two types of pollers for fetching services to create DNS records:

1. **Docker Poller**: Retrieves services directly from Docker.
1. **Traefik Poller**: Fetches services managed by Traefik.

Pollers are responsible for fetching available services and passing them to the sync service.

#### Docker

`dns-synchub` will discover running Docker containers by searching for supported labels.

To assign multiple DNS records to a single container, use the following format, similar to how Traefik defines routes:

```bash
  - traefik.http.routers.example.rule=Host(`example1.domain.tld`) || Host(`example2.domain.tld`)
```

##### Docker Options

| Parameter               | Description                                      | Type    | Default |
| ----------------------- | ------------------------------------------------ | ------- | ------- |
| `ENABLE_DOCKER_POLL`    | Enable or disable Docker polling.                | `BOOL`  | `TRUE`  |
| `DOCKER_TIMEOUT_SECONDS`| Timeout for HTTP calls to Docker API.            | `INT`   | `5`     |
| `DOCKER_POLL_SECONDS`   | Polling interval in seconds.                     | `INT`   | `30`    |

##### Filtering (Docker exclusively)

| Parameter               | Description                            | Type  | Default              |
| ----------------------- | -------------------------------------- | ----- | -------------------- |
| `DOCKER_FILTER_LABEL`   | A Pattern to filter Traefik label.     | `STR` | `traefik.constraint` |
| `DOCKER_FILTER_VALUE`   | A Pattern to filter Traefik values.    | `STR` | `.*`                 |

> **Note:** If `DOCKER_FILTER_VALUE` is not defined, `dns-snchub` will not filter containers based on `DOCKER_FILTER_LABEL`. If it is defined, `dns-synchub` will apply the specified pattern, and only the services that match this pattern will be used to update DNS records.

#### Traefik

To enable Traefik Polling mode, set the following environment variables:

- `ENABLE_TRAEFIK_POLL=TRUE`
- `TRAEFIK_POLL_URL=http://<host>:<port>`

In this mode, `dns-synchub` will poll Traefik every 30 seconds by default. During each poll, it will discover routers and include hosts that match the following criteria:

1. The provider is not Docker.
1. The status is enabled.
1. The name is present.
1. The rule contains `Host(...)`.
1. The host matches the include patterns (default: `.*`).
1. The host does not match the exclude patterns (default: none).

The polling interval can be adjusted by setting the `TRAEFIK_POLL_SECONDS` environment variable to the desired number of seconds (e.g., `TRAEFIK_POLL_SECONDS=120`).

##### Traefik Options

| Parameter                | Description                                      | Type                        | Default              |
| ------------------------ | ------------------------------------------------ | --------------------------- | -------              |
| `ENABLE_TRAEFIK_POLL`    | Enable or disable Traefik polling.               | `bool`                      | `False`              |
| `TRAEFIK_TIMEOUT_SECONDS`| Timeout for HTTP calls to Traefik API.           | `int`                       | `5`                  |
| `TRAEFIK_POLL_SECONDS`   | Polling interval in seconds.                     | `int`                       | `30`                 |
| `TRAEFIK_POLL_URL`       | URL for Traefik polling.                         | `str`                       | `N/A`                |

#### Synchronization Settings

The synchronization settings control how `dns-synchub` interacts with the DNS provider and manages DNS records. At this time. only Cloudflare is supported.

Key configuration options include:

| Parameter       | Description                          | Type             | Default |
|-----------------|--------------------------------------|------------------|---------|
| `TARGET_DOMAIN` | The target domain for DNS records.   | `STR`            | `N/A`   |
| `DEFAULT_TTL`   | Default Time-To-Live for DNS records.| `INT`            | `1`\[^1\] |
| `PROXIED`       | Whether the DNS record is proxied.   | `BOOL`           | `TRUE`  |
| `RC_TYPE`       | Type of DNS record (e.g., CNAME).    | `A, AAAA, CNAME` | `CNAME` |
| `ZONE_ID`       | Domain Zone ID                       | `STR`            | `N/A`   |

\[^1\]: If `1` is set, the TTL will be configured automatically based on the DNS provider's settings. For example, Cloudflare sets the TTL to 30 seconds for paid accounts and 60 seconds for free accounts.

##### Configuring Domain Options

Environment variables prefixed with `DOMAIN` enable customization of DNS record creation. For more details, see the [Configuring DNS Record Updates](#configuring-dns-record-updates) section.

| Parameter                             | Description                                              | Type   | Default |
| ------------------------------------- | -------------------------------------------------------- | ------ | ------- |
| `DOMAIN__<XXX>__NAME`                 | The domain name for which you wish to update records.    | `STR`  |         |
| `DOMAIN__<XXX>__COMMENT`              | (Optional) Comment for the DNS record.                   | `STR`  | `NONE`  |
| `DOMAIN__<XXX>__EXCLUDED_SUB_DOMAINS` | Specify subdomain trees to be ignored in labels\[^2\].     | `LIST` | `[]`    |

The following optional parameters may also be defined to customize domain update behavior, otherwise, default values will be used:

- `DOMAIN__<XXX>__ZONE_ID`
- `DOMAIN__<XXX>__PROXIED`
- `DOMAIN__<XXX>__TTL`
- `DOMAIN__<XXX>__TARGET_DOMAIN`
- `DOMAIN__<XXX>__RC_TYPE`

\[^2\]: For example, specifying `int` would prevent the creation of a CNAME for `*.int.example.com`.

##### Host Filtering Configuration

For detailed usage information, please refer to the [Pattern Matching](#pattern-matching) section.

| Parameter               | Description                                      | Type                | Default |
|-------------------------|--------------------------------------------------|---------------------|---------|
| `INCLUDED_HOSTS__<XXX>` | List of regex patterns for included hosts.       | `list[re.Pattern]`  | `[]`    |
| `EXCLUDED_HOSTS__<XXX>` | List of regex patterns for excluded hosts.       | `list[re.Pattern]`  | `[]`    |

#### Cloudflare

- `CF_TOKEN`: The Cloudflare API token for authentication. Ensure this token has the necessary permissions to manage DNS records for the specified domain.
- `CF_SYNC_INTERVAL`: The interval, in seconds, at which the synchronization process updates DNS records. Default is `300` seconds.

## Maintenance

### Shell Access

For debugging and maintenance purposes, you may want to access the container's shell. Shell access will be available only on testing `:test` images.

```bash
docker exec -it <container name> bash
```

### Telemetry

We use [OpenTelemetry](https://opentelemetry.io/)  for logging and metrics to ensure comprehensive observability of our services. This enables performance monitoring, issue detection, and insights into application behavior. Telemetry is disabled by default.

#### Setup

To configure [OpenTelemetry](https://opentelemetry.io/), follow these steps:

1. **Set Environment Variables**:

   Ensure that the necessary environment variables are set for OpenTelemetry to function correctly:

   ```bash
   export OTEL_EXPORTER_OTLP_ENDPOINT="your-otlp-endpoint"
   export OTEL_RESOURCE_ATTRIBUTES="service.name=your-service-name"
   ```

1. **Enable Telemetry**

Telemetry is disabled by default. To enable it, pass the `--enable-telemetry` argument at the command line.

## Support

For assistance with these Docker images, including troubleshooting, reporting bugs, or requesting new features, please refer to our support resources. You can submit bug reports and feature requests through our issue tracker. We are∫ committed to addressing issues promptly and considering feature requests for future updates. For additional help, consult the documentation or reach out to the community for guidance.

### Bug Reporting

If you encounter any issues, please submit a [Bug Report](issues/new). We prioritize and address reported issues as promptly as possible.

### Feature Requests

You are welcome to submit feature requests. Please note that there is no guarantee of inclusion or a specific timeline for implementation.

### Release Updates

We strive to track upstream changes, prioritizing images actively used in production. Fresh images for tagged releases are automatically published every 15 days to mitigate third-party vulnerabilities. Test images are updated with every commit and labeled with `:test`.

## License

MIT. See [LICENSE](LICENSE) for more details.

## References

- <https://www.cloudflare.com>
- <https://github.com/inean/dns-synchub>
- <https://github.com/code5-lab/dns-flare>
