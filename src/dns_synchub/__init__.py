from .__about__ import __version__ as VERSION
from .logger import get_default_logger, set_default_logger
from .mappers import CloudFlareMapper
from .pollers import DockerPoller, TraefikPoller
from .settings import Settings

__version__ = VERSION

__all__ = [
    # logger subpackage
    'get_default_logger',
    'set_default_logger',
    # settings subpackage
    'Settings',
    # pollers subpackage
    'DockerPoller',
    'TraefikPoller',
    # mappers subpackage
    'CloudFlareMapper',
]


def __dir__() -> list[str]:
    return sorted(__all__)
