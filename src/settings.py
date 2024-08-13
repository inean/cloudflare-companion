import re
from typing import Literal

# Inject custom methods into EventSettingsSource tu get support for:
# - _FIELD  like env vars
# -  List based submodules so FOO__0__KEY=VALUE will be converted to FOO=[{'KEY': 'VALUE'}]
#
from internal._settings import _EnvSettingsSource
from pydantic import BaseModel, field_validator, model_validator
from pydantic_settings import BaseSettings, EnvSettingsSource, SettingsConfigDict
from typing_extensions import Self

EnvSettingsSource.get_field_value = _EnvSettingsSource.get_field_value
EnvSettingsSource.explode_env_vars = _EnvSettingsSource.explode_env_vars

# Define the type alias
RecordType = Literal["A", "AAAA", "CNAME"]


class DomainsModel(BaseModel):
    name: str
    zone_id: str
    proxied: bool = True
    ttl: int | None = None
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

    # Docker Settings
    enable_docker_poll: bool = True
    docker_poll_seconds: int = 5

    # Traefik Settings
    enable_traefik_poll: bool = False
    traefik_poll_url: str | None = None
    traefik_poll_seconds: int = 5
    traefik_filter_value: str | None = None
    traefik_filter_label: str | None = None
    traefik_included_hosts: list[re.Pattern] = []
    traefik_excluded_hosts: list[re.Pattern] = []

    # Cloudflare Settings
    cf_token: str
    cf_email: str | None = None  # If not set, we are using scoped API

    # Cloudflare Default DNS Settings
    target_domain: str | None = None
    default_ttl: int = 1
    proxied: bool = True
    rc_type: RecordType = "CNAME"

    domains: list[DomainsModel] = []

    @field_validator("default_ttl", mode="before")
    def validate_ttl(cls, value):
        if value != 1 and value < 30:
            raise ValueError("TTL must be at least 30 seconds or 1 to auto")
        return value

    @model_validator(mode="after")
    def update_domains(self) -> Self:
        for dom in self.domains:
            dom.ttl = self.validate_ttl(dom.ttl or self.default_ttl)
            dom.target_domain = dom.target_domain or self.target_domain
            dom.rc_type = dom.rc_type or self.rc_type
            dom.proxied = dom.proxied or self.proxied
        return self

    @model_validator(mode="after")
    def update_traefik_domains(self) -> Self:
        if len(self.traefik_included_hosts) == 0:
            self.traefik_included_hosts.append(re.compile(".*"))
        return self

    @model_validator(mode="after")
    def sanity_options(self) -> Self:
        if self.enable_traefik_poll and not self.traefik_poll_url:
            raise ValueError("Traefik Polling is enabled but no URL is set")
        return self
