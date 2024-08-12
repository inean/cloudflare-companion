import asyncio
import logging
import os
import re
import sys
from datetime import datetime
from functools import lru_cache

import docker
import docker.errors
from settings import Settings
from typing_extensions import override

from pollers import DataPoller, PollerSource


class DockerContainer:
    def __init__(self, container: dict, *, logger: logging.Logger):
        self.container = container
        self.logger = logger

    @property
    def id(self) -> str | None:
        return self.container.attrs.get("Id")

    @property
    def labels(self) -> dict[str, str]:
        return self.container.attrs.get("Config", {}).get("Labels", {})

    def __getattr__(self, name: str) -> str | None:
        return self.labels.get(name)

    @property
    @lru_cache
    def hosts(self) -> list[str]:
        # Try to find traefik filter. If found, tray to parse

        for label, value in self.labels.items():
            if re.match(r"traefik.*?\.rule", label):
                self.logger.debug(f"Skipping label {label} from container {self.id}")
                continue
            if "Host" not in value:
                self.logger.debug(f"Skipping container {self.id} - Missing Host")
                continue

            # Extract the domains from the rule
            # hosts = re.findall(r"\`([a-zA-Z0-9\.\-]+)\`", value)
            hosts = re.findall(r"Host\(`([^`]+)`\)", value)
            self.logger.debug(f"Docker Route Name: {self.id} domains: {hosts}")
            return [hosts] if isinstance(hosts, str) else hosts

        return []


class DockerPoller(DataPoller):
    source = PollerSource.DOCKER

    def __init__(self, logger, *, settings: Settings, client: docker.DockerClient | None = None):
        try:
            # Init Docker client if not provided
            logger.debug("Connecting to Docker")
            client = client or docker.from_env(timeout=settings.docker_poll_seconds)
        except docker.errors.DockerException as e:
            logger.error(f"Could not connect to Docker: {e}")
            logger.error(f"Known DOCKER_HOST env is '{os.getenv('DOCKER_HOST') or ''}'")
            sys.exit(1)

        # Initialize the Poller
        super(DockerPoller, self).__init__(logger, settings=settings, client=client)

        # Computed from settings
        self.poll_sec = settings.docker_poll_seconds
        self.filter_label = re.compile(settings.traefik_filter_label)
        self.filter_value = re.compile(settings.traefik_filter_value)

    def _is_enabled(self, container: DockerContainer):
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
        return data, PollerSource.DOCKER

    @override
    async def _watch(self, timeout: float | None = None):
        since = datetime.now().strftime("%s")
        while True:
            until = datetime.now().strftime("%s")
            event = self.client.events(
                since=since,
                until=until,
                filters={"Type": "service", "Action": "update", "status": "start"},
                decode=True,
            )
            try:
                if any(event.get("status") == "start" for event in event):
                    self.logger.debug("Fetching routers from Docker API")
                    container = await asyncio.to_thread(self.client.containers.get, event.get("id"))
                    self.set_data(self._validate(container))
                    self.emit()
                await asyncio.sleep(self.poll_sec)
            except docker.errors.NotFound:
                pass
            except asyncio.CancelledError:
                self.logger.info("Polling has been cancelled. Performing cleanup.")
                pass

    @override
    async def fetch(self) -> list[DockerContainer]:
        return [
            DockerContainer(container, logger=self.logger)
            for container in self.client.containers.list(
                filters={
                    "status": "running",
                },
            )
        ]
