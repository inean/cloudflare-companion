# [DNS SncHub](github.com/inean/dns-synchub)

[![GitHub Container Registry](https://img.shields.io/badge/GitHub%20Container%20Registry-available-brightgreen?style=flat-square&logo=github)](https://github.com/inean/dns-synchub/pkgs/container/dns-synchub)
[![CI](https://github.com/inean/dns-synchub/actions/workflows/containers.yml/badge.svg)](https://github.com/inean/dns-synchub/actions/workflows/containers.yml)
[![codecov](https://codecov.io/github/inean/dns-synchub/graph/badge.svg?token=LHEA7AKBW0)](https://codecov.io/github/inean/dns-synchub)
[![Mergify Status](https://img.shields.io/endpoint.svg?url=https://api.mergify.com/v1/badges/inean/dns-synchub&style=flat-square)](https://mergify.io)

## About

This project builds a container image to automatically update zone providers (currently only [Cloudflare](https://www.cloudflare.com/) DNS records) upon container start when using [Traefik](https://github.com/traefik/traefik) as a reverse proxy.

This work is a rewrite of [docker-traefik-cloudflare-companion](https://github.com/tiredofit/docker-traefik-cloudflare-companion), maintained by [Dave Conroy](https://github.com/tiredofit/).

## Maintainer

- [Carlos Martín](https:/github.com/inean)

## Table of Contents

- [About](#about)
- [Maintainer](#maintainer)
- [Table of Contents](#table-of-contents)
- [Prerequisites and Assumptions](#prerequisites-and-assumptions)
- [Installation](#installation)
  - [Build from Source](#build-from-source)
  - [Prebuilt Images](#prebuilt-images)
    - [Multi Architecture](#multi-architecture)
- [Configuration](#configuration)
  - [Quick Start](#quick-start)
  - [Persistent Storage](#persistent-storage)
  - [Environment Variables](#environment-variables)
    - [Base Images used](#base-images-used)
    - [Container Options](#container-options)
    - [Docker Options](#docker-options)
    - [Cloudflare Options](#cloudflare-options)
    - [Traefik Options](#traefik-options)
    - [Docker Secrets](#docker-secrets)
  - [Discovery](#discovery)
    - [Docker](#docker)
    - [Docker Swarm](#docker-swarm)
    - [Traefik Polling](#traefik-polling)
      - [Filtering](#filtering)
        - [Include Patterns](#include-patterns)
        - [Exclude Patterns](#exclude-patterns)
        - [By Label (Docker Endpoint only)](#by-label-docker-endpoint-only)
- [Maintenance](#maintenance)
  - [Shell Access](#shell-access)
- [Support](#support)
  - [Usage](#usage)
  - [Bugfixes](#bugfixes)
  - [Feature Requests](#feature-requests)
  - [Updates](#updates)
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

| Container OS           | Tag       |
| ---------------------- | --------- |
| python-`<version>`-slim  | `:latest` |

The current Python version is specified in the `.python-version` file.

#### Multi-Architecture Support

Images are primarily tested on `arm64` architecture. Currently, the available architectures are `arm64` and `amd64`. Other variants, if available, are unsupported. To verify multi-architecture support for this image, use the command: `docker manifest inspect <image>:<tag>`.

## Configuration

### Quick Start

- The quickest way to get started is using [docker-compose](https://docs.docker.com/compose/). See the examples folder for a working [compose.yml](examples/compose.yml) that can be modified for development or production use.

- Set various [environment variables](#environment-variables) to understand the capabilities of this image.

Upon startup the image looks for a label containing `traefik.frontend.rule` (version 1) or `Host*` (version2) from your running containers of either updates Cloudflare with a CNAME record of your `TARGET_DOMAIN`. Previous versions of this container used to only update one Zone, however with the additional of the `DOMAIN` environment variables it now parses the containers variables and updates the appropriate zone.

For those wishing to assign multiple CNAMEs to a container use the following format:

- Traefik 1.x

````bash
  - traefik.normal.frontend.rule=Host:example1.domain.tld,example2.domain.tld
````

- Traefik 2.x

````bash
  - traefik.http.routers.example.rule=Host(`example1.domain.tld`) || Host(`example2.domain.tld`)
````

### Persistent Storage

| File                   | Description                                                              |
| ---------------------- | ------------------------------------------------------------------------ |
| `/var/run/docker.sock` | You must have access to the docker socket in order to utilize this image |

* * *

### Environment Variables

#### Base Images used

This image relies on an [Alpine Linux](https://hub.docker.com/r/inean/alpine) base image that relies on an [init system](https://github.com/just-containers/s6-overlay) for added capabilities. Outgoing SMTP capabilities are handlded via `msmtp`. Individual container performance monitoring is performed by [zabbix-agent](https://zabbix.org). Additional tools include: `bash`,`curl`,`less`,`logrotate`, `nano`.

Be sure to view the following repositories to understand all the customizable options:

| Image                                              | Description                            |
| -------------------------------------------------- | -------------------------------------- |
| [OS Base](https://github.com/inean/docker-alpine/) | Customized Image based on Alpine Linux |

#### Container Options

| Parameter   | Description                                                         | Default   |
| ----------- | ------------------------------------------------------------------- | --------- |
| `DRY_RUN`   | Perform a test run without making any changes `TRUE` or `FALSE`     | `FALSE`   |
| `LOG_LEVEL` | Logging Level `INFO` `VERBOSE` `DEBUG`                              | `INFO`    |
| `LOG_TYPE`  | Log Type `CONSOLE` `FILE` `BOTH`                                    | `BOTH`    |
| `LOG_FILE`  | Log Filename                                                        | `tcc.log` |
| `LOG_PATH`  | Log Path                                                            | `/logs/`  |
| `TCC_USER`  | User to run application as (there is a user `tcc` that can be used) | `root`    |

#### Docker Options

| Parameter           | Description                                                                             | Default                      |
| ------------------- | --------------------------------------------------------------------------------------- | ---------------------------- |
| `DOCKER_ENTRYPOINT` | Docker Entrypoint default (local mode)                                                  | `unix://var/run/docker.sock` |
| `DOCKER_HOST`       | (optional) If using tcp connection e.g. `tcp://111.222.111.32:2376`                     |                              |
| `DOCKER_CERT_PATH`  | (optional) If using tcp connection with TLS - Certificate location e.g. `/docker-certs` |                              |
| `DOCKER_SWARM_MODE` | Enable Docker Swarm Mode `TRUE` or `FALSE`                                              | `FALSE`                      |
| `DOCKER_TLS_VERIFY` | (optional) If using tcp conneciton to socket Verify TLS                                 | `1`                          |

#### Cloudflare Options

| Parameter                      | Description                                                                                                                                          | Default |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| `CF_EMAIL`                     | Email address tied to Cloudflare Account - Leave Blank for Scoped API                                                                                |         |
| `CF_TOKEN`                     | API Token for the Domain                                                                                                                             |         |
| `RC_TYPE`                      | Record Type for The Cloudflare e.g. `A;CNAME;AAAA`                                                                                                   | CNAME   |
| `TARGET_DOMAIN`                | Destination Hostname/IP to forward records to e.g. `host.example.com or 172.30.0.1`                                                                  |         |
| `DOMAIN1`                      | Domain 1 you wish to update records for.                                                                                                             |         |
| `DOMAIN1_ZONE_ID`              | Domain 1 Zone ID from Cloudflare                                                                                                                     |         |
| `DOMAIN1_PROXIED`              | Domain 1 True or False if proxied                                                                                                                    |         |
| `DOMAIN1_TARGET_DOMAIN`        | (optional specify target_domain for Domain 1, overriding the default value from TARGET_DOMAIN)                                                       |         |
| `DOMAIN1_EXCLUDED_SUB_DOMAINS` | (optional specify sub domain trees to be ignored in lables) ex: `DOMAIN1_EXCLUDED_SUB_DOMAINS=int` would not create a CNAME for `*.int.example.com`  |         |
| `DOMAIN2`                      | (optional Domain 2 you wish to update records for.)                                                                                                  |         |
| `DOMAIN2_ZONE_ID`              | Domain 2 Zone ID from Cloudflare                                                                                                                     |         |
| `DOMAIN2_PROXIED`              | Domain 1 True or False if proxied                                                                                                                    |         |
| `DOMAIN2_TARGET_DOMAIN`        | (optional specify target_domain for Domain 2, overriding the default value from TARGET_DOMAIN)                                                       |         |
| `DOMAIN2_EXCLUDED_SUB_DOMAINS` | (optional specify sub domain trees to be ignored in lables) ex: `DOMAIN2_EXCLUDED_SUB_DOMAINS=int` would not create a CNAME for `*.int.example2.com` |         |
| `DOMAIN3....`                  | And so on..                                                                                                                                          |         |
| `DEFAULT_TTL`                  | TTL to apply to records (1 = automatic, valid values: 60-86400 or 30-86400 for enterprise)                                                           | `1`     |

#### Traefik Options

| Parameter                  | Description                                                                      | Default              |
| -------------------------- | -------------------------------------------------------------------------------- | -------------------- |
| `TRAEFIK_VERSION`          | What version of Traefik do you want to work against - `1` or `2`                 | `2`                  |
| `ENABLE_TRAEFIK_POLL`      | Enable Traefik Polling Mode `TRUE` or `FALSE`                                    | `FALSE`              |
| `TRAEFIK_POLL_URL`         | (optional) If using Traefik Polling mode - URL to Traefik API endpoint           |                      |
| `TRAEFIK_POLL_SECONDS`     | (optional) If using Traefik Polling mode - Seconds to delay between poll attemps | `60`                 |
| `TRAEFIK_FILTER_LABEL`     | (optional) Filter by this label                                                  | `traefik.constraint` |
| `TRAEFIK_FILTER`           | (optional) Filter by above Label and Value                                       |                      |
| `TRAEFIK_INCLUDED_HOST1`   | (optional) If using Traefik Polling mode - Regex patterns for hosts to include   | `.*`                 |
| `TRAEFIK_INCLUDED_HOST...` | (optional traefik host include pattern 2 - N)                                    |                      |
| `TRAEFIK_EXCLUDED_HOST1`   | (optional) If using Traefik Polling mode - Regex patterns for hosts to exclude   |                      |
| `TRAEFIK_EXCLUDED_HOST...` | (optional traefik host exclude pattern 2 - N)                                    |                      |
| `REFRESH_ENTRIES`          | If record exists, update entry with new values `TRUE` or `FALSE`                 | `FALSE`              |

#### Docker Secrets

`CF_EMAIL` and `CF_TOKEN` support Docker Secrets
Name your secrets either CF_EMAIL and CF_TOKEN or cf_email and cf_token.

### Discovery

cloudflare-companion supports three different discovery mode: Docker, Docker Swarm, and Traefik Polling.  The Docker discovery mode is the only mode enabled by default.  Once matching hosts are discovered, cloudflare-companion will add or update CNAMEs in CloudFlare that point to the configured `TARGET_DOMAIN`.

#### Docker

cloudflare-companion will discover running Docker containers by searching for supported labels.

The supported labels are:

| Traefik Version | Single Host                                                       | Multiple Host                                                               |
| --------------- | ----------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `1`             | `traefik.normal.frontend.rule=Host:example1.domain.tld`           | `traefik.normal.frontend.rule=Host:example1.domain.tld,example2.domain.tld` |
| `2`             | ``traefik.http.routers.example.rule=Host(`example1.domain.tld`)`` | ``traefik.http.routers.example.rule=Host(`example1.domain.tld`)             |  | Host(`example2.domain.tld`)`` |

#### Docker Swarm

Docker Swarm mode can be enabled by setting the environment variable `SWARM_MODE=TRUE`.  This will cause cloudflare-companion to discover running Docker Swarm services with supported labels.

The supported labels are:

| Traefik Version | Single Host                                                       | Multiple Host                                                               |
| --------------- | ----------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `1`             | `traefik.normal.frontend.rule=Host:example1.domain.tld`           | `traefik.normal.frontend.rule=Host:example1.domain.tld,example2.domain.tld` |
| `2`             | ``traefik.http.routers.example.rule=Host(`example1.domain.tld`)`` | ``traefik.http.routers.example.rule=Host(`example1.domain.tld`)             |  | Host(`example2.domain.tld`)`` |

#### Traefik Polling

Traefik Polling mode can be enabled by setting the environment variable `TRAEFIK_VERSION=2`, `ENABLE_TRAEFIK_POLL=TRUE`, and `TRAEFIK_POLL_URL=http://<host>:<port>`.  This will cause cloudflare-companion to poll Traefik every 60s (default) and discover routers and include hosts which match the following rules:

1. Provider is not docker
2. Status is enabled
3. Name is present
4. Rule contains Host(...)
5. Host matches include patterns (default: .*)
6. Host does not match exclude patterns (default: none)

The polling interval can be configured by setting the environment variable `TRAEFIK_POLL_SECONDS=120`.

##### Filtering

Discovered hosts are matched against include and exclude patterns to determine if they should be included in the sync to CloudFlare.  By default, all found hosts are included.  Exclude patterns are higher priority than include patterns.  The defaults can be changed by configuring include and exclude patterns.

###### Include Patterns

Include patterns can be specified by defining one or more `TRAEFIK_INCLUDED_HOST<XXX>` variables such as `TRAEFIK_INCLUDED_HOST1=.*-data\.foobar\.com` and `TRAEFIK_INCLUDED_HOST2=.*-api\.foobar\.com`.  The pattern is a regular expression that is used to determine if the host should be included.

###### Exclude Patterns

Exclude patterns can be specified by defining one or more `TRAEFIK_EXCLUDED_HOST<XXX>` variables such as `TRAEFIK_EXCLUDED_HOST1=private-data\.foobar\.com` and `TRAEFIK_EXCLUDED_HOST2=.*-internal-api\.foobar\.com`.  The pattern is a regular expression that is used to determine if the host should be excluded.  Exclude patterns filter out results after include patterns are executed.

###### By Label (Docker Endpoint only)

If both `TRAEFIK_FILTER_LABEL` and `TRAEFIK_FILTER` are set only operate on containers with these matching values. This is useful if running multiple copies of Traefik and multiple copies of Cloudflare companion on your system or cluster or to limit acting on specific containers. Example:

````
TRAEFIK_CONSTRAINT_LABEL=traefik.constraint
TRAEFIK_CONSTRAINT=proxy-public
````

In your serving container:

````
services:
  nginx:
    image: inean/nginx:latest
    deploy:
      labels:
        - traefik.enable=true
        - traefik.http.routers.nginx.rule=Host(`nginx.example.com`)
        - ...
        - traefik.constraint=proxy-public
````

## Maintenance

### Shell Access

For debugging and maintenance purposes you may want access the containers shell.

```bash
docker exec -it (whatever your container name is e.g. traefik-cloudflare-companion) bash
```

## Support

These images were built to serve a specific need in a production environment and gradually have had more functionality added based on requests from the community.

### Usage

- The [Discussions board](../../discussions) is a great place for working with the community on tips and tricks of using this image.
- [Sponsor me](https://inean.ca/sponsor) for personalized support.

### Bugfixes

- Please, submit a [Bug Report](issues/new) if something isn't working as expected. I'll do my best to issue a fix in short order.

### Feature Requests

- Feel free to submit a feature request, however there is no guarantee that it will be added, or at what timeline.
- [Sponsor me](https://inean.ca/sponsor) regarding development of features.

### Updates

- Best effort to track upstream changes, More priority if I am actively using the image in a production environment.
- [Sponsor me](https://inean.ca/sponsor) for up to date releases.

## License

MIT. See [LICENSE](LICENSE) for more details.

## References

- <https://www.cloudflare.com>
- <https://github.com/inean/dns-synchub>
- <https://github.com/code5-lab/dns-flare>
