#!/usr/bin/env python3

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from datetime import datetime
from typing import TypedDict

import docker
import docker.errors
import logger as logger
import requests
from __about__ import __version__ as VERSION
from manager import DataManager
from mappers import CloudFlareMapper
from pollers import DockerPoller, PollerSource, TraefikPoller
from pydantic import ValidationError
from settings import Settings
from typing_extensions import deprecated


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


@deprecated("Use TraefikPoller")
class TraefikLegacyPoller(TraefikPoller):
    @deprecated("Use run instead")
    def check_traefik(self):
        def is_matching(host, patterns):
            return any(pattern.match(host) for pattern in patterns)

        mappings = {}
        self.logger.debug("Called check_traefik poller")
        response = requests.get(self.poll_url)

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
    def check_traefik_and_sync_mappings(self, domain_infos):
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
        sync_mappings(self.settings, traefik_mappings, domain_infos)


@deprecated("Use TraefikPoller instead")
def check_traefik(
    settings, included_hosts: list[re.Pattern], excluded_hosts: list[re.Pattern], logger
):
    settings.traefik_included_hosts = included_hosts
    settings.traefik_excluded_hosts = excluded_hosts
    poller = TraefikLegacyPoller(logger, settings=settings)
    return poller.check_traefik()


@deprecated("Use TraefikPoller instead")
def check_traefik_and_sync_mappings(settings, included_hosts, excluded_hosts, domain_infos, logger):
    settings.traefik_included_hosts = included_hosts
    settings.traefik_excluded_hosts = excluded_hosts
    poller = TraefikLegacyPoller(logger, settings=settings)
    poller.check_traefik_and_sync_mappings(included_hosts, excluded_hosts, domain_infos)


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
def sync_mappings(settings, mappings, domain_infos, logger):
    """
    Synchronizes the mappings with the domain information.

    Args:
        mappings (dict): The mappings to synchronize.
        domain_infos (dict): Domain information for synchronization.
    """
    for k, v in mappings.items():
        current_mapping = synced_mappings.get(k)
        if current_mapping is None or current_mapping > v:
            if CloudFlareMapper.point_domain(settings, k, domain_infos, logger):
                synced_mappings[k] = v


def get_initial_mappings(client, settings: Settings, included_hosts, excluded_hosts, logger):
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
        traefik_mappings = check_traefik(settings, included_hosts, excluded_hosts, logger)
        # Add the extracted mappings to the current mappings
        add_to_mappings(mappings, traefik_mappings)

    return mappings


@deprecated("Use DockerPoller instead")
def check_container_t2(containers: list | None, settings, logger):
    mappings = {}

    client = DockerPoller(logger, settings=settings)
    if containers is None:
        containers = asyncio.run(client.fetch())
    for container in containers or []:
        if client._is_enabled(container):
            for host in container.hosts:
                mappings[host] = 1

    return mappings


@deprecated("Use DockerPoller instead")
async def watch_events(dk_agent, settings):
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
                    container = await asyncio.to_thread(dk_agent.containers.get, event.get("id"))
                    add_to_mappings(
                        new_mappings,
                        check_container_t2(container, settings, logger),
                    )
                except docker.errors.NotFound:
                    forever = 778
                    pass
        sync_mappings(settings, new_mappings, settings.domains, logger)
        t = t_next
        await asyncio.sleep(5)  # Sleep for 5 seconds before checking for new events


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
    log = logger.initialize_logger(settings)
    logger.report_current_status_and_settings(log, settings)

    # Init agents
    manager = DataManager(logger=log)

    # Docker poller
    if settings.enable_docker_poll:
        poller = DockerPoller(log, settings=settings)
        manager.add_poller(poller)
        dk_agent = poller.client

    # Traefik poller
    if settings.enable_traefik_poll:
        poller = TraefikPoller(log, settings=settings)
        manager.add_poller(poller)

    # Init mappings
    mappings = get_initial_mappings(
        dk_agent,
        settings,
        settings.traefik_included_hosts,
        settings.traefik_excluded_hosts,
    )
    sync_mappings(settings, mappings, settings.domains)

    # Start traefik polling on a separate thread
    polls = []
    if settings.enable_traefik_poll:
        log.debug("Starting traefik router polling")
        traefik_poll = AsyncRepeatedTimer(
            settings.traefik_poll_seconds,
            check_traefik_and_sync_mappings,
            args=(
                settings,
                settings.traefik_included_hosts,
                settings.traefik_excluded_hosts,
                settings.domains,
                logger,
            ),
        )
        polls.append(traefik_poll.start())

    # Start docker polleer
    if settings.enable_docker_poll:
        docker_poll = asyncio.create_task(watch_events(dk_agent, settings))
        polls.append(docker_poll)

    # Run pollers in parallel
    try:
        await manager.start()
    except asyncio.CancelledError:
        log.info("Pollers were stopped...")


def parse_args():
    parser = argparse.ArgumentParser(description="Cloudflare Companion")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.get_logger().info("Exiting...")
        for task in asyncio.all_tasks():
            task.cancel()
        sys.exit(0)
    except Exception as e:
        logger.get_logger().error(f"An error occurred: {e}")
        sys.exit(1)
