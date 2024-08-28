import asyncio
import logging
import re
from datetime import datetime
from functools import lru_cache
from typing import Any, cast

import docker
from docker import DockerClient
from docker.errors import DockerException, NotFound
from docker.models.containers import Container
from typing_extensions import override

from dns_synchub.internal._decorators import retry
from dns_synchub.pollers import DataPoller, PollerSource
from dns_synchub.settings import Settings


class DockerError(Exception):
    def __init__(self, message: str, *, error: Exception | None = None):
        super().__init__(message)
        self.error = error


class DockerContainer:
    def __init__(self, container: Container, *, logger: logging.Logger):
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
                self.logger.debug(f"Malformed rule in container {self.id} - Missing Host")
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
        # Initialize the Poller
        super(DockerPoller, self).__init__(logger, settings=settings, client=client)

        # Computed from settings
        self.poll_sec = settings.docker_poll_seconds
        self.tout_sec = settings.docker_timeout_seconds

        # Special, Docker Only filter settings
        self.filter_label = settings.docker_filter_label
        self.filter_value = settings.docker_filter_value

    @property
    def client(self) -> DockerClient:
        if self._client is None:
            try:
                # Init Docker client if not provided
                self.logger.debug("Connecting to Docker...")
                self._client = docker.from_env(timeout=self.tout_sec)
            except Exception as err:
                self.logger.error(f"Could not connect to Docker: {err}")
                self.logger.error("Please make sure Docker is running and accessible")
                raise DockerError("Could not connect to Docker", error=err) from err
            else:
                # Get Docker Host info
                info = cast(dict[str, Any], self._client.info())  # type: ignore
                self.logger.debug(f"Connected to Docker Host at '{info.get('Name')}'")
        return self._client

    def _is_enabled(self, container: DockerContainer):
        # If no filter is set, return True
        if self.filter_label is None:
            return True
        # If a filter is set, check if the container matches
        assert isinstance(self.filter_label, re.Pattern)
        # Check if any label matches the filter
        for label, value in container.labels.items():
            # Check if label is present
            if self.filter_label.match(label):
                if self.filter_value is None:
                    return True
                # A filter value is also set, check if it matches
                assert isinstance(self.filter_value, re.Pattern)
                return self.filter_value.match(value)
        return False

    def _validate(self, raw_data: list[DockerContainer]) -> tuple[list[str], PollerSource]:
        data: list[str] = []
        for container in raw_data:
            # Check if container is enabled
            if not self._is_enabled(container):
                self.logger.debug(f"Skipping container {container.id}")
                continue
            # Validate domain and queue for sync
            for host in container.hosts:
                data.append(host)
        # Return a collection of zones to sync
        assert "source" in self.config
        return data, self.config["source"]

    @override
    async def _watch(self):
        until = datetime.now().strftime("%s")
        while True:
            since = until
            self.logger.debug("Fetching routers from Docker API")
            until = datetime.now().strftime("%s")
            # Ther's no swarm in podman engine, so remove Action filter
            filter = {"Type": "service", "status": "start"}
            kwargs = {"since": since, "until": until, "filters": filter, "decode": True}
            try:
                events = self.client.events(**kwargs)
                for event in events:
                    raw_data = self.client.containers.get(event.get("id"))
                    services = [DockerContainer(raw_data, logger=self.logger)]
                    self.events.set_data(self._validate(services))
            except NotFound:
                await self.events.emit()
                await asyncio.sleep(self.poll_sec)
            except asyncio.CancelledError:
                self.logger.info("Dokcker polling cancelled. Performing cleanup.")
                return
            finally:
                events.close()

    @override
    @retry
    def fetch(self) -> tuple[list[str], PollerSource]:
        try:
            raw_data = self.client.containers.list(filters={"status": "running"})
            services = [
                DockerContainer(container, logger=self.logger)
                for container in cast(list[Container], raw_data)
            ]
        except DockerException:
            services = []
        return self._validate(services)
