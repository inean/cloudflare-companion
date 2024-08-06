#!/usr/bin/env python3

from __future__ import print_function

import asyncio
import logging
import os
import re
import sys
import time
from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

import CloudFlare
import docker
import docker.errors
import requests

# Inject custom methods into EventSettingsSource tu get support for:
# - _FIELD  like env vars
# -  List based submodules so FOO__0__KEY=VALUE will be converted to FOO=[{'KEY': 'VALUE'}]
#
from _settings import _EnvSettingsSource
from pydantic import BaseModel, ValidationError, model_validator
from pydantic_settings import BaseSettings, EnvSettingsSource, SettingsConfigDict
from typing_extensions import Self

EnvSettingsSource.get_field_value = _EnvSettingsSource.get_field_value
EnvSettingsSource.explode_env_vars = _EnvSettingsSource.explode_env_vars


class AsyncRepeatedTimer:
    def __init__(
        self,
        interval: int,
        function: callable,
        *,
        args: tuple | None = None,
        kwargs: dict | None = None,
    ):
        self.interval = interval
        self.function = function
        self.args = args or []
        self.kwargs = kwargs or {}
        self.task = None

    async def _run(self):
        while True:
            await asyncio.sleep(self.interval)
            self.function(*self.args, **self.kwargs)

    def start(self):
        self.task = asyncio.create_task(self._run())
        return self.task

    def cancel(self):
        self.task and self.task.cancel()


class DomainsModel(BaseModel):
    name: str
    zone_id: str
    proxied: bool = True
    ttl: int | None = None
    target_domain: str | None = None
    comment: str | None = None
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

    # Source Settings
    source: Literal["docker", "podman"] = "docker"
    enable_docker_poll: bool = True

    # Traefik Settings
    enable_traefik_poll: bool = False
    traefik_filter: str | None = None
    traefik_filter_label: str = "traefik.constraint"
    refresh_entries: bool = False
    traefik_poll_seconds: int = 5
    traefik_poll_url: str | None = None
    traefik_included_hosts: list[re.Pattern] = []
    traefik_excluded_hosts: list[re.Pattern] = []

    # Cloudflare Settings
    cf_token: str
    target_domain: str

    cf_email: str | None = None  # If not set, we are using scoped API
    default_ttl: int = 1
    rc_type: str = "CNAME"
    domains: list[DomainsModel] = []

    @model_validator(mode="after")
    def update_domains(self) -> Self:
        for dom in self.domains:
            dom.ttl = dom.ttl or self.default_ttl
            dom.target_domain = dom.target_domain or self.target_domain
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


# set up logging
def initialize_logger(settings):
    # Extract attributes from settings and convert to uppercase
    log_level = settings.log_level.upper()
    log_type = settings.log_type.upper()
    log_file = settings.log_file

    # Set up logging
    logger = logging.getLogger(__name__)

    if log_level == "DEBUG":
        logger.setLevel(logging.DEBUG)
        fmt = "%(asctime)s %(levelname)s %(lineno)d | %(message)s"

    if log_level == "VERBOSE":
        logger.setLevel(logging.DEBUG)
        fmt = "%(asctime)s %(levelname)s | %(message)s"

    if log_level in ("NOTICE", "INFO"):
        logger.setLevel(logging.INFO)
        fmt = "%(asctime)s %(levelname)s | %(message)s"

    if log_type in ("CONSOLE", "BOTH"):
        ch = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(fmt, "%Y-%m-%dT%H:%M:%S%z")
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    if log_type in ("FILE", "BOTH"):
        try:
            fh = logging.FileHandler(log_file)
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        except OSError as e:
            logger.error(f"Could not open log file '{e.filename}': {e.strerror}")

    return logger


def is_domain_excluded(logger, name, dom: DomainsModel):
    for sub_dom in dom.excluded_sub_domains:
        fqdn_with_sub_dom = sub_dom + "." + dom.name

        if name.find(fqdn_with_sub_dom) != -1:
            logger.info(
                "Ignoring %s because it falls until excluded sub domain: %s",
                name,
                sub_dom,
            )
            return True

    return False


def is_matching(host, regexes):
    for regex in regexes:
        if regex.search(host):
            return True
    return False


# Start Program to update the Cloudflare
def point_domain(cf, settings, name, domain_infos: list[DomainsModel], logger):
    ok = True
    for domain_info in domain_infos:
        if name == domain_info.target_domain:
            continue

        if name.find(domain_info.name) >= 0:
            if is_domain_excluded(logger, name, domain_info):
                continue

            records = None
            retry = 0
            while retry < 5:  # maximum of 5 retries
                try:
                    records = cf.zones.dns_records.get(
                        domain_info.zone_id, params={"name": name}
                    )
                    break
                except CloudFlare.exceptions.CloudFlareAPIError as e:
                    if "Rate limited" in str(e):  # Check for rate limit error message
                        retry += 1
                        time.sleep(2**retry)  # Exponential backoff
                    else:
                        raise e

            if records is None:
                ok = False
                continue

            data = {
                "type": settings.rc_type,
                "name": name,
                "content": domain_info.target_domain,
                "ttl": int(domain_info.ttl),
                "proxied": domain_info.proxied,
                "comment": domain_info.comment,
            }
            if settings.refresh_entries:
                try:
                    if len(records) == 0:
                        if settings.dry_run:
                            logger.info(
                                "DRY-RUN: POST to Cloudflare %s:, %s",
                                domain_info.zone_id,
                                data,
                            )
                        else:
                            _ = cf.zones.dns_records.post(
                                domain_info.zone_id, data=data
                            )
                        logger.info(
                            "Created new record: %s to point to %s",
                            name,
                            domain_info.target_domain,
                        )
                    else:
                        for record in records:
                            if settings.dry_run:
                                logger.info(
                                    "DRY-RUN: PUT to Cloudflare %s, %s:, %s",
                                    domain_info.zone_id,
                                    record["id"],
                                    data,
                                )
                            else:
                                cf.zones.dns_records.put(
                                    domain_info.zone_id, record["id"], data=data
                                )
                            logger.info(
                                "Updated existing record: %s to point to %s",
                                name,
                                domain_info.target_domain,
                            )
                except CloudFlare.exceptions.CloudFlareAPIError as ex:
                    logger.error("** %s - %d %s" % (name, ex, ex))
                    ok = False
                    pass
            else:
                try:
                    if settings.dry_run:
                        logger.info(
                            "DRY-RUN: POST to Cloudflare %s:, %s",
                            domain_info.zone_id,
                            data,
                        )
                    else:
                        _ = cf.zones.dns_records.post(domain_info.zone_id, data=data)
                    logger.info(
                        "Created new record: %s to point to %s",
                        name,
                        domain_info.target_domain,
                    )
                except CloudFlare.exceptions.CloudFlareAPIError as ex:
                    logger.error("** %s - %d %s" % (name, ex, ex))
                    ok = False
    return ok


def check_container_t2(c, settings):
    def label_host():
        for prop in c.attrs.get("Config").get("Labels"):
            value = c.attrs.get("Config").get("Labels").get(prop)
            if re.match(r"traefik.*?\.rule", prop):
                if "Host" in value:
                    logger.debug("Container ID: %s rule value: %s", cont_id, value)
                    extracted_domains = re.findall(r"\`([a-zA-Z0-9\.\-]+)\`", value)
                    logger.debug(
                        "Container ID: %s extracted domains from rule: %s",
                        cont_id,
                        extracted_domains,
                    )
                    if len(extracted_domains) > 1:
                        for v in extracted_domains:
                            logger.info(
                                "Found Service ID: %s with Multi-Hostname %s",
                                cont_id,
                                v,
                            )
                            mappings[v] = 1
                    elif len(extracted_domains) == 1:
                        logger.info(
                            "Found Service ID: %s with Hostname %s",
                            cont_id,
                            extracted_domains[0],
                        )
                        mappings[extracted_domains[0]] = 1
                else:
                    pass

    mappings = {}
    logger.debug("Called check_container_t2 for: %s", c)
    cont_id = c.attrs.get("Id")
    try:
        settings.traefik_filter
    except NameError:
        label_host()
    else:
        for filter_label in c.attrs.get("Config").get("Labels"):
            filter_value = c.attrs.get("Config").get("Labels").get(filter_label)
            if re.match(settings.traefik_filter_label, filter_label) and re.match(
                settings.traefik_filter, filter_value
            ):
                logger.debug(
                    f"Found Container ID {cont_id} with matching label {filter_label} with value {filter_value}"
                )
                label_host()
    return mappings


def check_traefik(settings, included_hosts, excluded_hosts):
    mappings = {}
    logger.debug("Called check_traefik poller")
    r = requests.get("{}/api/http/routers".format(settings.traefik_poll_url))
    if r.ok:
        for router in r.json():
            if "status" in router and router["status"] == "enabled":
                if "name" in router and "rule" in router:
                    name = router["name"]
                    value = router["rule"]
                    if "Host" in value:
                        logger.debug(
                            "Traefik Router Name: %s rule value: %s", name, value
                        )
                        extracted_domains = re.findall(
                            r"Host\(\`([a-zA-Z0-9\.\-]+)\`\)", value
                        )
                        logger.debug(
                            "Traefik Router Name: %s extracted domains from rule: %s",
                            name,
                            extracted_domains,
                        )
                        if len(extracted_domains) > 1:
                            for v in extracted_domains:
                                if is_matching(v, included_hosts):
                                    if is_matching(v, excluded_hosts):
                                        logger.debug(
                                            "Traefik Router Name: %s with Multi-Hostname %s - Matched Exclude",
                                            name,
                                            v,
                                        )
                                    else:
                                        logger.info(
                                            "Found Traefik Router Name: %s with Multi-Hostname %s",
                                            name,
                                            v,
                                        )
                                        mappings[v] = 2
                                else:
                                    logger.debug(
                                        "Traefik Router Name: %s with Multi-Hostname %s: Not Match Include",
                                        name,
                                        v,
                                    )
                        elif len(extracted_domains) == 1:
                            if is_matching(extracted_domains[0], included_hosts):
                                if is_matching(extracted_domains[0], excluded_hosts):
                                    logger.debug(
                                        "Traefik Router Name: %s with Hostname %s - Matched Exclude",
                                        name,
                                        extracted_domains[0],
                                    )
                                else:
                                    logger.info(
                                        "Found Traefik Router Name: %s with Hostname %s",
                                        name,
                                        extracted_domains[0],
                                    )
                                    mappings[extracted_domains[0]] = 2
                            else:
                                logger.debug(
                                    "Traefik Router Name: %s with Hostname %s: Not Match Include",
                                    name,
                                    extracted_domains[0],
                                )

    return mappings


def check_traefik_and_sync_mappings(
    cf, settings, included_hosts, excluded_hosts, domain_infos
):
    """
    Checks Traefik for mappings and syncs them with the domain information.

    Args:
        included_hosts (list): List of hosts to include.
        excluded_hosts (list): List of hosts to exclude.
        domain_infos (dict): Domain information for synchronization.
    """
    # Extract mappings from Traefik
    traefik_mappings = check_traefik(settings, included_hosts, excluded_hosts)
    # Sync the extracted mappings with the domain information
    sync_mappings(cf, settings, traefik_mappings, domain_infos)


def add_to_mappings(current_mappings, mappings):
    """
    Adds new mappings to the current mappings if they meet the criteria.

    Args:
        current_mappings (dict): The current mappings.
        mappings (dict): The new mappings to add.
    """
    for k, v in mappings.items():
        current_mapping = current_mappings.get(k)
        if current_mapping is None or current_mapping > v:
            current_mappings[k] = v


synced_mappings = {}


def sync_mappings(cf, settings, mappings, domain_infos, logger):
    """
    Synchronizes the mappings with the domain information.

    Args:
        mappings (dict): The mappings to synchronize.
        domain_infos (dict): Domain information for synchronization.
    """
    for k, v in mappings.items():
        current_mapping = synced_mappings.get(k)
        if current_mapping is None or current_mapping > v:
            if point_domain(cf, settings, k, domain_infos, logger):
                synced_mappings[k] = v


def get_initial_mappings(client, settings, included_hosts, excluded_hosts):
    """
    Initializes the mappings by discovering Docker containers and Traefik services.

    Args:
        included_hosts (list): List of hosts to include.
        excluded_hosts (list): List of hosts to exclude.

    Returns:
        dict: The initial mappings.
    """
    logger.debug("Starting Initialization Routines")

    mappings = {}
    if settings.enable_docker_poll:
        for c in client.containers.list():
            logger.debug("Container List Discovery Loop")
            add_to_mappings(mappings, check_container_t2(c, settings))

    if settings.traefik_poll_url:
        logger.debug("Traefik List Discovery Loop")
        # Extract mappings from Traefik
        traefik_mappings = check_traefik(settings, included_hosts, excluded_hosts)
        # Add the extracted mappings to the current mappings
        add_to_mappings(mappings, traefik_mappings)

    return mappings


def uri_valid(x):
    try:
        result = urlparse(x)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


def report_current_status_and_settings(logger: logging.Logger, settings: Settings):
    if settings.dry_run:
        logger.warning(f"Dry Run: {settings.dry_run}")
    logger.debug(f"Docker Polling: {settings.enable_docker_poll}")
    logger.debug(f"Refresh Entries: {settings.refresh_entries}")
    logger.debug(f"Default TTL: {settings.default_ttl}")

    if settings.enable_traefik_poll:
        if uri_valid(settings.traefik_poll_url):
            logger.debug("Traefik Poll Url: %s", settings.traefik_poll_url)
            logger.debug("Traefik Poll Seconds: %s", settings.traefik_poll_seconds)
        else:
            settings.enable_traefik_poll = False
            logger.error(
                "Traefik Polling Mode disabled because traefik url is invalid: %s",
                settings.traefik_poll_url,
            )

    logger.debug("Traefik Polling Mode: %s", False)

    for dom in settings.domains:
        logger.debug("Domain Configuration: %s", dom)


def init_cloudflare_agent(logger: logging.Logger, settings: Settings):
    # Init Cloudflare client
    cf_debug = settings.log_level.upper() == "VERBOSE"
    if not settings.cf_email:
        logger.debug("API Mode: Scoped")
        cf = CloudFlare.CloudFlare(debug=cf_debug, token=settings.cf_token)
    else:
        logger.debug("API Mode: Global")
        cf = CloudFlare.CloudFlare(
            debug=cf_debug, email=settings.cf_email, token=settings.cf_token
        )
    return cf


def init_docker_agent(logger: logging.Logger, settings: Settings):
    # Init Docker client
    try:
        client = docker.from_env()
    except docker.errors.DockerException as e:
        logger.error(f"Could not connect to Docker: {e}")
        logger.error(f"Known DOCKER_HOST env is '{os.getenv('DOCKER_HOST') or ''}'")
        sys.exit(1)

    logger.debug("Connected to Docker")
    return client


async def watch_events(dk_agent, cf_agent, settings):
    t = datetime.now().strftime("%s")

    logger.debug("Starting event watch docker events")
    logger.debug("Time: %s", t)
    forever = 0

    while forever < 777:
        logger.debug("Called docker poller")
        t_next = datetime.now().strftime("%s")
        events = dk_agent.events(
            since=t,
            until=t_next,
            filters={"Type": "service", "Action": "update", "status": "start"},
            decode=True,
        )
        new_mappings = {}
        for event in events:
            if event.get("status") == "start":
                try:
                    container = await asyncio.to_thread(
                        dk_agent.containers.get, event.get("id")
                    )
                    add_to_mappings(
                        new_mappings,
                        check_container_t2(container, settings),
                    )
                except docker.errors.NotFound:
                    forever = 778
                    pass
        sync_mappings(cf_agent, settings, new_mappings, settings.domains, logger)
        t = t_next
        await asyncio.sleep(5)  # Sleep for 5 seconds before checking for new events


logger = None


def get_logger():
    return logger


async def main():
    # Load settings
    try:
        settings = Settings()  # type: ignore[call-arg]

        # Check for uppercase docker secrets or env variables
        assert settings.cf_token
        assert settings.target_domain
        assert len(settings.domains) > 0

    except ValidationError as e:
        print(f"Unable to load settings: {e}", file=sys.stderr)
        sys.exit(1)

    # Set up logging and dump runtime settings
    global logger
    logger = initialize_logger(settings)
    report_current_status_and_settings(logger, settings)

    # Init agents
    cf_agent = init_cloudflare_agent(logger, settings)
    dk_agent = None
    if settings.enable_docker_poll:
        dk_agent = init_docker_agent(logger, settings)

    # Init mappings
    mappings = get_initial_mappings(
        dk_agent,
        settings,
        settings.traefik_included_hosts,
        settings.traefik_excluded_hosts,
    )
    sync_mappings(cf_agent, settings, mappings, settings.domains)

    # Start traefik polling on a separate thread
    polls = []
    if settings.enable_traefik_poll:
        logger.debug("Starting traefik router polling")
        traefik_poll = AsyncRepeatedTimer(
            settings.traefik_poll_seconds,
            check_traefik_and_sync_mappings,
            args=(
                cf_agent,
                settings,
                settings.traefik_included_hosts,
                settings.traefik_excluded_hosts,
                settings.domains,
            ),
        )
        polls.append(traefik_poll.start())

    # Start docker polleer
    if settings.enable_docker_poll:
        docker_poll = asyncio.create_task(watch_events(dk_agent, cf_agent, settings))
        polls.append(docker_poll)

    # Run pollers in parallel
    try:
        await asyncio.gather(*polls)
    except asyncio.CancelledError:
        logger.info("Pollers were stopped...")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Exiting...")
        for task in asyncio.all_tasks():
            task.cancel()
        sys.exit(0)
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        sys.exit(1)
