# src/dns_synchub/__init__.py

from .__about__ import __version__ as VERSION
from .logger import get_logger, initialize_logger
from .mappers import CloudFlareMapper
from .pollers import DockerPoller, TraefikPoller
from .settings import Settings

__version__ = VERSION

__all__ = [
    # logger subpackage
    'get_logger',
    'initialize_logger',
    # settings subpackage
    'Settings',
    # pollers subpackage
    'DockerPoller',
    'TraefikPoller',
    # mappers subpackage
    'CloudFlareMapper',
]


def __dir__() -> 'list[str]':
    return list(__all__)
