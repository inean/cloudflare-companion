import re
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self

# Define the type alias
RecordType = Literal["A", "AAAA", "CNAME"]


def validate_ttl(value: int | Literal["auto"]) -> int | Literal["auto"]:
    if isinstance(value, int) and value >= 30:
        return value
    if value == "auto":
        return value
    raise ValueError("TTL must be at least 30 seconds or 'auto'")


TTLType = Annotated[int | str, BeforeValidator(validate_ttl)]

PollerSourceType = Literal["manual", "docker", "traefik"]


class DomainsModel(BaseModel):
    name: str
    zone_id: str
    proxied: bool = True
    ttl: TTLType | None = None
    target_domain: str | None = None
    comment: str | None = None
    rc_type: RecordType | None = None
    excluded_sub_domains: list[str] = []


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        validate_default=False,
        extra="ignore",
        secrets_dir="/var/run",
        env_file=(".env", ".env.prod"),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )

    # Settings
    dry_run: bool = False
    log_file: str = "/logs/tcc.log"
    log_level: str = "INFO"
    log_type: str = "BOTH"
    refresh_entries: bool = False

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
    traefik_excluded_providers: list[str] = ["docker"]

    # Mapper Settings
    target_domain: str | None = None
    zone_id: str | None = None
    default_ttl: TTLType = "auto"
    proxied: bool = True
    rc_type: RecordType = "CNAME"

    included_hosts: list[re.Pattern[str]] = []
    excluded_hosts: list[re.Pattern[str]] = []

    # Cloudflare Settings
    cf_token: str | None = None
    cf_sync_seconds: int = 300  # Sync interval in seconds
    cf_timeout_seconds: int = 30  # Timeout for blocking requests operations

    domains: list[DomainsModel] = []

    @model_validator(mode="after")
    def update_domains(self) -> Self:
        for dom in self.domains:
            dom.ttl = dom.ttl or self.default_ttl
            dom.target_domain = dom.target_domain or self.target_domain
            dom.rc_type = dom.rc_type or self.rc_type
            dom.proxied = dom.proxied or self.proxied
        return self

    @model_validator(mode="after")
    def add_default_include_host(self) -> Self:
        if len(self.included_hosts) == 0:
            self.included_hosts.append(re.compile(".*"))
        return self

    @model_validator(mode="after")
    def sanity_options(self) -> Self:
        if self.enable_traefik_poll and not self.traefik_poll_url:
            raise ValueError("Traefik Polling is enabled but no URL is set")
        return self

    @model_validator(mode="after")
    def enforce_tokens(self) -> Self:
        if self.dry_run or self.cf_token:
            return self
        raise ValueError("Missing Cloudflare API token. Provide it or enable dry-run mode.")
