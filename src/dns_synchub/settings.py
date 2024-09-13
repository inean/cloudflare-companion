import logging
import re
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from dns_synchub.types import (
    DomainsModel,
    LogHandlersType,
    LogLevelType,
    RecordType,
    TTLType,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        validate_default=False,
        extra='ignore',
        secrets_dir='/var/run',
        env_file=('.env', '.env.prod'),
        env_file_encoding='utf-8',
        env_nested_delimiter='__',
    )

    # Settings
    dry_run: bool = False
    verbose: bool = False

    # Telemetry Settings
    service_name: str = 'dns-synchub'
    log_level: LogLevelType = logging.INFO
    log_handlers: set[LogHandlersType] = {'otlp', 'stderr'}
    log_file: str = '/logs/dns-synchub.log'

    @property
    def log_formatter(self) -> logging.Formatter:
        fmt = '%(asctime)s | %(message)s'
        if self.verbose:
            fmt = '%(asctime)s %(levelname)s %(lineno)d | %(message)s'
        elif logging.DEBUG == self.log_level:
            fmt = '%(asctime)s %(levelname)s | %(message)s'
        return logging.Formatter(fmt, '%Y-%m-%dT%H:%M:%S%z')

    # Poller Common settings

    # Docker Settings
    enable_docker_poll: bool = True
    docker_timeout_seconds: int = 5  # Timeout for requests based Docker client operations
    docker_poll_seconds: int = 30  # Polling interval in seconds
    docker_filter_value: re.Pattern[str] | None = None
    docker_filter_label: re.Pattern[str] | None = None

    # Traefik Settings
    enable_traefik_poll: bool = False
    traefik_poll_url: str | None = None
    traefik_poll_seconds: int = 30  # Polling interval in seconds
    traefik_timeout_seconds: int = 5  # Timeout for blocking requests operations
    traefik_excluded_providers: list[str] = ['docker']

    # Mapper Settings
    target_domain: str | None = None
    zone_id: str | None = None
    default_ttl: TTLType = 'auto'
    proxied: bool = True
    rc_type: RecordType = 'CNAME'
    refresh_entries: bool = False

    included_hosts: list[re.Pattern[str]] = []
    excluded_hosts: list[re.Pattern[str]] = []

    # Cloudflare Settings
    cf_token: str | None = None
    cf_sync_seconds: int = 300  # Sync interval in seconds
    cf_timeout_seconds: int = 30  # Timeout for blocking requests operations

    domains: list[DomainsModel] = []

    @model_validator(mode='after')
    def update_domains(self) -> Self:
        for dom in self.domains:
            dom.ttl = dom.ttl or self.default_ttl
            dom.target_domain = dom.target_domain or self.target_domain
            dom.rc_type = dom.rc_type or self.rc_type
            dom.proxied = dom.proxied or self.proxied
        return self

    @model_validator(mode='after')
    def add_default_include_host(self) -> Self:
        if len(self.included_hosts) == 0:
            self.included_hosts.append(re.compile('.*'))
        return self

    @model_validator(mode='after')
    def sanity_options(self) -> Self:
        if self.enable_traefik_poll and not self.traefik_poll_url:
            raise ValueError('Traefik Polling is enabled but no URL is set')
        return self

    @model_validator(mode='after')
    def enforce_tokens(self) -> Self:
        if self.dry_run or self.cf_token:
            return self
        raise ValueError('Missing Cloudflare API token. Provide it or enable dry-run mode.')

    def __hash__(self) -> int:
        return id(self)
