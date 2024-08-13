import asyncio
import re

import requests
from settings import Settings
from typing_extensions import override

from pollers import DataPoller, PollerSource


class TraefikPoller(DataPoller[requests.Session]):
    source = PollerSource.TRAEFIK

    def __init__(self, logger, *, settings: Settings, client: requests.Session | None = None):
        # Initialize the Poller
        super(TraefikPoller, self).__init__(
            logger,
            settings=settings,
            client=client or requests.Session(),
        )
        # Computed from settings
        self.poll_sec = settings.traefik_poll_seconds
        self.poll_url = f"{settings.traefik_poll_url}/api/http/routers"

    def _is_valid_route(self, route):
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

    def _is_valid_host(self, host):
        if not any(pattern.match(host) for pattern in self.included_hosts):
            self.logger.debug(f"Traefik Router Host: {host} - Not Match with Include Hosts")
            return False
        if any(pattern.match(host) for pattern in self.excluded_hosts):
            self.logger.debug(f"Traefik Router Host: {host} - Match with Exclude Hosts")
            return False
        # Host is intended to be synced
        return True

    def _validate(self, raw_data: list[dict]) -> tuple[list[str], PollerSource]:
        data = []
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
        return data, PollerSource.TRAEFIK

    @override
    async def _watch(self, timeout: float | None = None):
        try:
            while True:
                self.logger.debug("Fetching routers from Traefik API")
                self.events.set_data(self.fetch())
                await self.events.emit()
                await asyncio.sleep(self.poll_sec)
        except asyncio.CancelledError:
            self.logger.info("Traefik Polling cancelled. Performing cleanup.")
            return

    @override
    def fetch(self) -> tuple[list[str, PollerSource]]:
        try:
            response = self.client.get(self.poll_url, timeout=self.poll_sec)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to fetch routers from Traefik API: {e}")
            response = None
            # Return a collection of routes
        return self._validate([] if response is None else response.json())
