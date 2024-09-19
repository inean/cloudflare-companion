import asyncio
from datetime import datetime
from functools import lru_cache
import logging
import re
from typing import Any, cast

import docker
from docker import DockerClient
from docker.errors import NotFound
from docker.models.containers import Container
import requests
import tenacity
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from typing_extensions import override

from dns_synchub.pollers import Poller, PollerData
from dns_synchub.settings import Settings
from dns_synchub.types import PollerSourceType


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
        return self.container.attrs.get('Id')

    @property
    def labels(self) -> Any:
        return self.container.attrs.get('Config', {}).get('Labels', {})

    def __getattr__(self, name: str) -> Any:
        if name in self.container.attrs:
            return self.container.attrs[name]
        return self.labels.get(name)

    @property
    @lru_cache
    def hosts(self) -> list[str]:
        # Try to find traefik filter. If found, tray to parse

        for label, value in self.labels.items():
            if not re.match(r'traefik.*?\.rule', label):
                continue
            self.logger.debug(f"Found traefik label '{label}' from container {self.id}")
            if 'Host' not in value:
                self.logger.debug(f'Malformed rule in container {self.id} - Missing Host')
                continue

            # Extract the domains from the rule
            # Host(`example.com`) => ['example.com']
            hosts = re.findall(r'Host\(`([^`]+)`\)', value)
            self.logger.debug(f"Found service '{self.Name}' with hosts: {hosts}")
            return hosts

        return []


class DockerPoller(Poller[DockerClient]):
    config = {**Poller.config, 'source': 'docker'}  # type: ignore

    def __init__(
        self,
        logger: logging.Logger,
        *,
        settings: Settings,
        client: DockerClient | None = None,
    ):
        # Computed from settings
        self.poll_sec = settings.docker_poll_seconds
        self.tout_sec = settings.docker_timeout_seconds

        # Special, Docker Only filter settings
        self.filter_label = settings.docker_filter_label
        self.filter_value = settings.docker_filter_value

        self._client: DockerClient | None = client

        # Initialize the Poller
        super().__init__(logger, settings=settings, client=client)

    @property
    def client(self) -> DockerClient:
        if self._client is None:
            try:
                # Init Docker client if not provided
                self.logger.debug('Connecting to Docker...')
                self._client = docker.from_env(timeout=self.tout_sec)
            except Exception as err:
                self._client = None
                self.logger.error(f'Could not connect to Docker: {err}')
                self.logger.error('Please make sure Docker is running and accessible')
                raise DockerError('Could not connect to Docker', error=err) from err
            else:
                # Get Docker Host info
                info = cast(dict[str, Any], self._client.info())  # type: ignore
                self.logger.debug(f"Connected to Docker Host at '{info.get('Name')}'")
        return self._client

    def _is_enabled(self, container: DockerContainer) -> bool:
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
                return self.filter_value.match(value) is not None
        return False

    def _validate(self, raw_data: list[DockerContainer]) -> PollerData[PollerSourceType]:
        hosts: list[str] = []
        for container in raw_data:
            # Check if container is enabled
            if not self._is_enabled(container):
                self.logger.debug(f'Skipping container {container.id}')
                continue
            # Validate domain and queue for sync
            for host in container.hosts:
                hosts.append(host)
        # Return a collection of zones to sync
        assert 'source' in self.config
        return PollerData[PollerSourceType](hosts, self.config['source'])

    @override
    async def _watch(self) -> None:
        until = datetime.now().strftime('%s')

        @retry(
            wait=wait_exponential(multiplier=self.config['wait'], max=self.poll_sec),
            retry=retry_if_exception_type(requests.exceptions.ConnectionError),
            before_sleep=lambda state: self.logger.error(
                f'Retry attept {state.attempt_number}: {state.outcome.exception() if state.outcome else None}'
            ),
        )
        async def fetch_events(kwargs: dict[str, Any]) -> Any:
            kwargs['until'] = datetime.now().strftime('%s')
            return await asyncio.to_thread(self.client.events, **kwargs)

        while True:
            since = until
            self.logger.debug('Fetching routers from Docker API')
            # Ther's no swarm in podman engine, so remove Action filter
            filter = {'Type': 'service', 'status': 'start'}
            kwargs = {'since': since, 'filters': filter, 'decode': True}
            events = None
            try:
                events = await fetch_events(kwargs)
                until = str(kwargs['until'])
                for event in events:
                    if 'id' not in event:
                        self.logger.warning('Container ID is None. Skipping container.')
                        continue
                    raw_data = await asyncio.to_thread(self.client.containers.get, event['id'])
                    services = [DockerContainer(raw_data, logger=self.logger)]
                    self.events.set_data(self._validate(services))
                else:
                    raise NotFound('No events found')
            except NotFound:
                await self.events.emit()
                await asyncio.sleep(self.poll_sec)
            except tenacity.RetryError as err:
                self.logger.error(f'Could not fetch events: {err.last_attempt.result()}')
                raise asyncio.CancelledError from err
            except asyncio.CancelledError:
                self.logger.info('Docker polling cancelled. Performing cleanup.')
                raise
            finally:
                _ = events and await asyncio.to_thread(events.close)

    @override
    async def fetch(self) -> PollerData[PollerSourceType]:
        filters = {'status': 'running'}
        stop = stop_after_attempt(self.config['stop'])
        wait = wait_exponential(multiplier=self.config['wait'], max=self.tout_sec)
        raw_data = []
        try:
            async for attempt_ctx in AsyncRetrying(stop=stop, wait=wait):
                with attempt_ctx:
                    try:
                        containers = self.client.containers
                        raw_data = await asyncio.to_thread(containers.list, filters=filters)
                        result = [DockerContainer(c, logger=self.logger) for c in raw_data]
                    except Exception as err:
                        att = attempt_ctx.retry_state.attempt_number
                        self.logger.debug(f'Docker.fetch attempt {att} failed: {err}')
                        raise
        except RetryError as err:
            last_error = err.last_attempt.result()
            self.logger.critical(f'Could not fetch containers: {last_error}')
        # Return a collection of routes
        return self._validate(result)
