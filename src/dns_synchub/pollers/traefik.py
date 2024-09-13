import asyncio
from logging import Logger
import re
from typing import Any

from requests import Response, Session
from tenacity import AsyncRetrying, RetryError, stop_after_attempt, wait_exponential
from typing_extensions import override

from dns_synchub.pollers import Poller, PollerData
from dns_synchub.settings import Settings
from dns_synchub.types import PollerSourceType


class TimeoutSession(Session):
    def __init__(self, *, timeout: float | None = None):
        self.timeout = timeout
        super().__init__()

    def request(self, method: str | bytes, url: str | bytes, *params: Any, **data: Any) -> Response:
        if 'timeout' not in data and self.timeout:
            data['timeout'] = self.timeout
        return super().request(method, url, *params, **data)


class TraefikPoller(Poller[Session]):
    config = {**Poller.config, 'source': 'traefik'}  # type: ignore

    def __init__(self, logger: Logger, *, settings: Settings, client: Session | None = None):
        # Computed from settings
        self.poll_sec = settings.traefik_poll_seconds
        self.tout_sec = settings.traefik_timeout_seconds
        self.poll_url = f'{settings.traefik_poll_url}/api/http/routers'

        # Providers filtering
        self.excluded_providers = settings.traefik_excluded_providers

        # Initialize the Poller
        client = client or TimeoutSession(timeout=self.tout_sec)
        super().__init__(logger, settings=settings, client=client)

    def _is_valid_route(self, route: dict[str, Any]) -> bool:
        # Computed from settings
        required_keys = ['status', 'name', 'rule']
        if any(key not in route for key in required_keys):
            self.logger.debug(f'Traefik Router Name: {route} - Missing Key')
            return False
        if route['status'] != 'enabled':
            self.logger.debug(f"Traefik Router Name: {route['name']} - Not Enabled")
            return False
        if 'Host' not in route['rule']:
            self.logger.debug(f"Traefik Router Name: {route['name']} - Missing Host")
        # Route is valid and enabled
        return True

    def _is_valid_host(self, host: str) -> bool:
        if not any(pattern.match(host) for pattern in self.included_hosts):
            self.logger.debug(f'Traefik Router Host: {host} - Not Match with Include Hosts')
            return False
        if any(pattern.match(host) for pattern in self.excluded_hosts):
            self.logger.debug(f'Traefik Router Host: {host} - Match with Exclude Hosts')
            return False
        # Host is intended to be synced
        return True

    def _validate(self, raw_data: list[dict[str, Any]]) -> PollerData[PollerSourceType]:
        hosts: list[str] = []
        for route in raw_data:
            # Check if route is whell formed
            if not self._is_valid_route(route):
                continue
            # Extract the domains from the rule
            host_rules = re.findall(r'Host\(`([^`]+)`\)', route['rule'])
            self.logger.debug(f"Traefik Router Name: {route['name']} host: {host_rules}")
            # Validate domain and queue for sync
            for host in (host for host in host_rules if self._is_valid_host(host)):
                self.logger.info(f"Found Traefik Router: {route['name']} with Hostname {host}")
                hosts.append(host)
        # Return a collection of zones to sync
        assert 'source' in self.config
        return PollerData[PollerSourceType](hosts, self.config['source'])

    @override
    async def _watch(self) -> None:
        try:
            while True:
                self.logger.debug('Fetching routers from Traefik API')
                self.events.set_data(await self.fetch())
                await self.events.emit()
                await asyncio.sleep(self.poll_sec)
        except asyncio.CancelledError:
            self.logger.info('Traefik Polling cancelled. Performing cleanup.')
            return

    @override
    async def fetch(self) -> PollerData[PollerSourceType]:
        stop = stop_after_attempt(self.config['stop'])
        wait = wait_exponential(multiplier=self.config['wait'], max=self.tout_sec)
        rawdata = []
        assert self._client
        try:
            async for attempt_ctx in AsyncRetrying(stop=stop, wait=wait):
                with attempt_ctx:
                    try:
                        response = await asyncio.to_thread(self._client.get, self.poll_url)
                        response.raise_for_status()
                        rawdata = response.json()
                    except Exception as err:
                        att = attempt_ctx.retry_state.attempt_number
                        self.logger.debug(f'Traefik.fetch attempt {att} failed: {err}')
                        raise
        except RetryError as err:
            last_error = err.last_attempt.result()
            self.logger.critical(f'Failed to fetch route from Traefik API: {last_error}')
        # Return a collection of routes
        return self._validate(rawdata)
