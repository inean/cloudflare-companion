from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import TypedDict

import docker
import docker.errors
import requests
from .manager import DataManager
from .mappers import CloudFlareMapper
from .pollers import DockerPoller, PollerSource, TraefikPoller
from .settings import Settings
from typing_extensions import deprecated


class AsyncRepeatedTimer:
    def __init__(
        self,
        function: callable,
        interval: int,
        *,
        args: tuple | None = None,
        kwargs: dict | None = None,
    ):
        self.interval = interval
        self.function = function
        self.args = args or []
        self.kwargs = kwargs or {}
        self.task = None

    async def run(self):
        while True:
            await asyncio.sleep(self.interval)
            self.function(*self.args, **self.kwargs)


@deprecated("Use TraefikPoller")
class TraefikLegacyPoller(TraefikPoller):
    @deprecated("Use run instead")
    def check_traefik(self):
        def is_matching(host, patterns):
            return any(pattern.match(host) for pattern in patterns)

        mappings = {}
        self.logger.debug("Called check_traefik poller")
        try:
            response = requests.get(self.poll_url)
        except requests.exceptions.ConnectionError as e:
            # Extracting the URL and the error message for a shorter log message
            self.logger.error(f"Error while fetching Traefik data: {str(e)}")
            return mappings

        if response is not None and response.ok:
            for router in response.json():
                if any(key not in router for key in ["status", "name", "rule"]):
                    self.logger.debug(f"Traefik Router Name: {router} - Missing Key")
                    continue
                if router["status"] != "enabled" or "Host" not in router["rule"]:
                    self.logger.debug(
                        f"Traefik Router Name: {router['name']} - Not Enabled or Missing Host"
                    )
                    continue

                # Extract the domains from the rule
                name, value = router["name"], router["rule"]
                self.logger.debug(f"Traefik Router Name: {name} rule value: {value}")

                # Extract the domains from the rule
                extracted_domains = re.findall(r"Host\(`([^`]+)`\)", value)
                self.logger.debug(f"Traefik Router Name: {name} domains: {extracted_domains}")

                for v in extracted_domains:
                    if not is_matching(v, self.included_hosts):
                        self.logger.debug(
                            f"Traefik Router Name: {name} with Host {v}: Not Match Include"
                        )
                        continue
                    if is_matching(v, self.excluded_hosts):
                        self.logger.debug(
                            f"Traefik Router Name: {name} with Host {v} - Match exclude"
                        )
                        continue
                    # Matched
                    self.logger.info(f"Found Traefik Router Name: {name} with Hostname {v}")
                    mappings[v] = 2

        return mappings

    @deprecated("Use run instead")
    def check_traefik_and_sync_mappings(self, mapper, domain_infos, log):
        """
        Checks Traefik for mappings and syncs them with the domain information.

        Args:
            included_hosts (list): List of hosts to include.
            excluded_hosts (list): List of hosts to exclude.
            domain_infos (dict): Domain information for synchronization.
        """
        # Extract mappings from Traefik
        traefik_mappings = self.check_traefik()
        # Sync the extracted mappings with the domain information
        sync_mappings(mapper, traefik_mappings, domain_infos)


@deprecated("Use TraefikPoller instead")
def check_traefik(
    settings, included_hosts: list[re.Pattern], excluded_hosts: list[re.Pattern], logger
):
    settings.traefik_included_hosts = included_hosts
    settings.traefik_excluded_hosts = excluded_hosts
    poller = TraefikLegacyPoller(logger, settings=settings)
    return poller.check_traefik()


@deprecated("Use TraefikPoller instead")
def check_traefik_and_sync_mappings(
    traefik_poller,
    mapper,
    settings,
    included_hosts,
    excluded_hosts,
    domain_infos,
    logger,
):
    settings.traefik_included_hosts = included_hosts
    settings.traefik_excluded_hosts = excluded_hosts
    poller = TraefikLegacyPoller(logger, settings=settings)
    poller.check_traefik_and_sync_mappings(mapper, domain_infos, logger)


class ZoneUpdateJob(TypedDict, total=False):
    timestamp: int
    """Timestamp of the job. Use time.monotonic_ns()"""

    source: PollerSource
    """Poller that provide the job"""

    entries: list[str]
    """List of entries to update"""


synced_mappings = {}


@deprecated("Use SyncManager instead")
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


@deprecated("Use SyncManager instead")
def sync_mappings(mapper: CloudFlareMapper, mappings, domain_infos):
    """
    Synchronizes the mappings with the domain information.

    Args:
        mappings (dict): The mappings to synchronize.
        domain_infos (dict): Domain information for synchronization.
    """
    for name, v in mappings.items():
        current_mapping = synced_mappings.get(name)
        if current_mapping is None or current_mapping > v:
            if mapper.point_domain(name, domain_infos):
                synced_mappings[name] = v


def get_initial_mappings(
    docker_poller: DockerPoller,
    traefik_poller: TraefikLegacyPoller,
    settings: Settings,
    logger,
):
    logger.debug("Starting Initialization Routines")

    mappings = {}
    if docker_poller and settings.enable_docker_poll:
        for c in docker_poller.client.containers.list():
            logger.debug("Docker Container List Discovery Loop")
            add_to_mappings(mappings, check_container_t2(docker_poller, c))

    if traefik_poller and settings.traefik_poll_url:
        logger.debug("Traefik List Discovery Loop")
        # Extract mappings from Traefik
        traefik_mappings = traefik_poller.check_traefik()
        # Add the extracted mappings to the current mappings
        add_to_mappings(mappings, traefik_mappings)

    return mappings


@deprecated("Use DockerPoller instead")
def check_container_t2(poller: DockerPoller, containers: list | None):
    mappings = {}

    if containers is None:
        containers = asyncio.run(poller.fetch())
    for container in containers or []:
        if poller._is_enabled(container):
            for host in container.hosts:
                mappings[host] = 1

    return mappings


@deprecated("Use DockerPoller instead")
async def watch_events(poller: DockerPoller, mapper: CloudFlareMapper, domains):
    t = datetime.now().strftime("%s")

    poller.logger.debug("Starting event watch docker events")
    poller.logger.debug("Time: %s", t)
    forever = 0

    while forever < 777:
        poller.logger.debug("Called docker poller")
        t_next = datetime.now().strftime("%s")
        events = poller.client.events(
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
                        poller.client.containers.get, event.get("id")
                    )
                    add_to_mappings(new_mappings, check_container_t2(poller, container))
                except docker.errors.NotFound:
                    forever = 778
                    pass
        sync_mappings(mapper, new_mappings, domains)
        t = t_next
        await asyncio.sleep(5)  # Sleep for 5 seconds before checking for new events


async def legacy_main(log: logging.Logger, *, settings: Settings):
    tasks = []
    mappings = {}

    # Add Cloudflarte mapper
    cf = CloudFlareMapper(log, settings=settings)

    # Traefik poller
    if settings.enable_traefik_poll:
        # Start traefik polling on a separate thread
        log.debug("(Legacy): Starting traefik router polling")
        # Add traefik poller
        traefik = TraefikLegacyPoller(log, settings=settings)

        # Get initial mappings
        log.debug("Traefik List Discovery Loop")
        # Extract mappings from Traefik
        traefik_mappings = traefik.check_traefik()
        # Add the extracted mappings to the current mappings
        add_to_mappings(mappings, traefik_mappings)

        # Start legacy poller
        tasks.append(
            asyncio.create_task(
                AsyncRepeatedTimer(
                    traefik.check_traefik_and_sync_mappings,
                    settings.traefik_poll_seconds,
                    args=(cf, settings.domains, log),
                ).run()
            )
        )

    # Docker poller
    if settings.enable_docker_poll:
        log.debug("(Legacy): Starting poller router polling")
        poller = DockerPoller(log, settings=settings)

        # Get initial mappings
        for container in poller.client.containers.list():
            log.debug("Docker Container List Discovery Loop")
            add_to_mappings(mappings, check_container_t2(poller, container))

        # Start legacy poller
        tasks.append(asyncio.create_task(watch_events(poller, settings, log)))

    # Publish mappings
    sync_mappings(cf, mappings, settings.domains)

    # Run pollers in parallel
    await asyncio.gather(*tasks)


async def main(log: logging.Logger, *, settings: Settings):
    # Init mnager
    manager = DataManager(logger=log)

    # Add Cloudflarte mapper
    cf = CloudFlareMapper(log, settings=settings)
    await manager.add_mapper(cf, backoff=5)

    # Add Pollers
    if settings.enable_traefik_poll:
        poller = TraefikPoller(log, settings=settings)
        manager.add_poller(poller)
    if settings.enable_docker_poll:
        poller = DockerPoller(log, settings=settings)
        manager.add_poller(poller)

    # Start manager
    await manager.start()
