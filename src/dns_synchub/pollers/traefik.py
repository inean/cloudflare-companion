import asyncio
import re
from logging import Logger
from typing import Any

from requests import Session
from tenacity import AsyncRetrying, RetryError, stop_after_attempt, wait_exponential
from typing_extensions import override

from dns_synchub.pollers import Poller
from dns_synchub.settings import PollerSourceType, Settings


class TimeoutSession(Session):
    def __init__(self, *, timeout: float | None = None):
        self.timeout = timeout
        super().__init__()

    def request(self, *args: Any, **kwargs: dict[str, Any]):
        if "timeout" not in kwargs and self.timeout:
            kwargs["timeout"] = self.timeout  # type: ignore
        return super().request(*args, **kwargs)


class TraefikPoller(Poller[Session]):
    config = {**Poller.config, "source": "traefik"}

    def __init__(self, logger: Logger, *, settings: Settings, client: Session | None = None):
        # Computed from settings
        self.poll_sec = settings.traefik_poll_seconds
        self.tout_sec = settings.traefik_timeout_seconds
        self.poll_url = f"{settings.traefik_poll_url}/api/http/routers"

        # Providers filtering
        self.excluded_providers = settings.traefik_excluded_providers

        # Initialize the Poller
        client = client or TimeoutSession(timeout=self.tout_sec)
        super(TraefikPoller, self).__init__(logger, settings=settings, client=client)

    def _is_valid_route(self, route: dict[str, Any]) -> bool:
        # Computed from settings
        required_keys = ["status", "name", "rule"]
        if any(key not in route for key in required_keys):
            self.logger.debug(f"Traefik Router Name: {route} - Missing Key")
            return False
        if route["status"] != "enabled":
            self.logger.debug(f"Traefik Router Name: {route['name']} - Not Enabled")
            return False
        if "Host" not in route["rule"]:
            self.logger.debug(f"Traefik Router Name: {route['name']} - Missing Host")
        # Route is valid and enabled
        return True

    def _is_valid_host(self, host: str) -> bool:
        if not any(pattern.match(host) for pattern in self.included_hosts):
            self.logger.debug(f"Traefik Router Host: {host} - Not Match with Include Hosts")
            return False
        if any(pattern.match(host) for pattern in self.excluded_hosts):
            self.logger.debug(f"Traefik Router Host: {host} - Match with Exclude Hosts")
            return False
        # Host is intended to be synced
        return True

    def _validate(self, raw_data: list[dict[str, Any]]) -> tuple[list[str], PollerSourceType]:
        data: list[str] = []
        for route in raw_data:
            # Check if route is whell formed
            if not self._is_valid_route(route):
                continue
            # Extract the domains from the rule
            hosts = re.findall(r"Host\(`([^`]+)`\)", route["rule"])
            self.logger.debug(f"Traefik Router Name: {route['name']} domains: {hosts}")
            # Validate domain and queue for sync
            for host in (host for host in hosts if self._is_valid_host(host)):
                self.logger.info(f"Found Traefik Router: {route['name']} with Hostname {host}")
                data.append(host)
        # Return a collection of zones to sync
        assert "source" in self.config
        return data, self.config["source"]

    @override
    async def _watch(self, timeout: float | None = None):
        try:
            while True:
                self.logger.debug("Fetching routers from Traefik API")
                self.events.set_data(await self.fetch())  # type: ignore
                await self.events.emit()
                await asyncio.sleep(self.poll_sec)
        except asyncio.CancelledError:
            self.logger.info("Traefik Polling cancelled. Performing cleanup.")
            return

    @override
    async def fetch(self) -> tuple[list[str], PollerSourceType]:
        stop = stop_after_attempt(self.config["stop"])
        wait = wait_exponential(multiplier=self.config["wait"], max=self.tout_sec)
        rawdata: Any = []
        assert self._client
        try:
            async for attempt in AsyncRetrying(stop=stop, wait=wait):
                with attempt:
                    response = self._client.get(self.poll_url)
                    response.raise_for_status()
                    rawdata = response.json()
        except RetryError as err:
            self.logger.critical(f"Failed to fetch route from Traefik API: {err}")
        # Return a collection of routes
        return self._validate(rawdata)
