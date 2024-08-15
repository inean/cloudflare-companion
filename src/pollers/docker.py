import asyncio
import logging
import os
import re
import sys
from datetime import datetime
from functools import lru_cache

import docker
from docker import DockerClient
from docker.errors import DockerException, NotFound
from docker.models.containers import Container
from internal._decorators import async_backoff
from settings import Settings
from typing_extensions import override

from pollers import DataPoller, PollerSource


class DockerContainer:
    def __init__(self, container: Container | dict, *, logger: logging.Logger):
        self.container = container
        self.logger = logger

    @property
    def id(self) -> str | None:
        return self.container.attrs.get("Id")

    @property
    def labels(self) -> dict[str, str]:
        return self.container.attrs.get("Config", {}).get("Labels", {})

    def __getattr__(self, name: str) -> str | None:
        if name in self.container.attrs:
            return self.container.attrs[name]
        return self.labels.get(name)

    @property
    @lru_cache
    def hosts(self) -> list[str]:
        # Try to find traefik filter. If found, tray to parse

        for label, value in self.labels.items():
            if not re.match(r"traefik.*?\.rule", label):
                continue
            self.logger.debug(f"Found traefik label '{label}' from container {self.id}")
            if "Host" not in value:
                self.logger.debug(f"Skipping container {self.id} - Missing Host")
                continue

            # Extract the domains from the rule
            # Host(`example.com`) => ['example.com']
            hosts = re.findall(r"Host\(`([^`]+)`\)", value)
            self.logger.debug(f"Found service '{self.Name}' with hosts: {hosts}")
            return hosts

        return []


class DockerPoller(DataPoller[DockerClient]):
    config = DataPoller.config | {
        "source": "docker",
    }

    def __init__(
        self,
        logger: logging.Logger,
        *,
        settings: Settings,
        client: DockerClient | None = None,
    ):
        try:
            # Init Docker client if not provided
            logger.debug("Connecting to Docker...")
            client = client or docker.from_env(timeout=settings.docker_timeout_seconds)
            logger.debug(f"Connected to Docker at '{client.info()['Name']}'")
        except DockerException as e:
            logger.error(f"Could not connect to Docker: {e}")
            logger.error(f"Known DOCKER_HOST env is '{os.getenv('DOCKER_HOST') or ''}'")
            sys.exit(1)

        # Initialize the Poller
        super(DockerPoller, self).__init__(logger, settings=settings, client=client)

        # Computed from settings
        self.poll_sec = settings.docker_poll_seconds
        self.filter_label = settings.traefik_filter_label
        self.filter_value = settings.traefik_filter_value

    def _is_enabled(self, container: DockerContainer):
        # If no filter is set, return True
        if self.filter_value is None:
            return True
        # If a filter is set, check if the container matches
        assert isinstance(self.filter_value, re.Pattern)
        assert isinstance(self.filter_label, re.Pattern)
        # Check if any label matches the filter
        for label, value in container.labels.items():
            if self.filter_label.match(label) and self.filter_value.match(value):
                return True
        return False

    def _validate(self, raw_data: list[DockerContainer]) -> tuple[list[str], PollerSource]:
        data = []
        for container in raw_data:
            # Check if container is enabled
            if not self._is_enabled(container):
                self.logger.debug(f"Skipping container {container.id}")
                continue
            # Validate domain and queue for sync
            for host in container.hosts:
                data.append(host)
        # Return a collection of zones to sync
        return data, self.config["source"]

    @override
    async def _watch(self, timeout: float | None = None):
        try:
            since = datetime.now().strftime("%s")
            while True:
                self.logger.debug("Fetching routers from Docker API")
                until = datetime.now().strftime("%s")
                # Ther's no swarm in podman engine, so remove Action filter
                fmask = {"Type": "service", "status": "start"}
                event = self.client.events(since=since, until=until, filters=fmask, decode=True)
                try:
                    if any(event.get("status") == "start" for event in event):
                        raw_data = self.client.containers.get(event.get("id"))
                        services = [DockerContainer(raw_data, logger=self.logger)]
                        self.events.set_data(self._validate(services))
                except NotFound:
                    pass
                finally:
                    await self.events.emit()
                    await asyncio.sleep(self.poll_sec)
        except asyncio.CancelledError:
            self.logger.info("Dokcker polling cancelled. Performing cleanup.")
            return

    @override
    @async_backoff
    def fetch(self) -> tuple[list[str], PollerSource]:
        raw_data = self.client.containers.list(filters={"status": "running"})
        services = [DockerContainer(container, logger=self.logger) for container in raw_data]
        return self._validate(services)
