from __future__ import annotations

import argparse
import logging

import dotenv

from dns_synchub.__about__ import __version__ as VERSION
from dns_synchub.manager import DataManager
from dns_synchub.mappers import CloudFlareMapper
from dns_synchub.pollers import DockerPoller, TraefikPoller
from dns_synchub.settings import Settings


def parse_args():
    parser = argparse.ArgumentParser(description="Cloudflare Companion")
    parser.add_argument("--env-file", type=str, help="Path to the .env file")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")

    args = parser.parse_args()
    args.env_file and dotenv.load_dotenv(args.env_file)  # type: ignore
    return args


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
