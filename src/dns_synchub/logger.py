from __future__ import annotations

import logging
import re
import sys

from .settings import Settings

logger = None


# set up logging
def initialize_logger(settings: Settings):
    global logger

    assert logger is None, "Logger already initialized"

    # Extract attributes from settings and convert to uppercase
    log_level = settings.log_level.upper()
    log_type = settings.log_type.upper()
    log_file = settings.log_file

    # Set up logging
    logger = logging.getLogger(__name__)

    fmt = None
    if log_level == "DEBUG":
        logger.setLevel(logging.DEBUG)
        fmt = "%(asctime)s %(levelname)s %(lineno)d | %(message)s"

    if log_level == "VERBOSE":
        logger.setLevel(logging.DEBUG)
        fmt = "%(asctime)s %(levelname)s | %(message)s"

    if log_level in ("NOTICE", "INFO"):
        logger.setLevel(logging.INFO)
        fmt = "%(asctime)s %(levelname)s | %(message)s"

    formatter = logging.Formatter(fmt, "%Y-%m-%dT%H:%M:%S%z")
    if log_type in ("CONSOLE", "BOTH"):
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    if log_type in ("FILE", "BOTH"):
        try:
            fh = logging.FileHandler(log_file)
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        except OSError as e:
            logger.error(f"Could not open log file '{e.filename}': {e.strerror}")

    return logger


def report_current_status_and_settings(logger: logging.Logger, settings: Settings):
    settings.dry_run and logger.info(f"Dry Run: {settings.dry_run}")  # type: ignore
    logger.debug(f"Default TTL: {settings.default_ttl}")
    logger.debug(f"Refresh Entries: {settings.refresh_entries}")

    logger.debug(f"Traefik Polling Mode: {'On' if settings.enable_traefik_poll else 'Off'}")
    if settings.enable_traefik_poll:
        if settings.traefik_poll_url and re.match(r"^\w+://[^/?#]+", settings.traefik_poll_url):
            logger.debug(f"Traefik Poll Url: {settings.traefik_poll_url}")
            logger.debug(f"Traefik Poll Seconds: {settings.traefik_poll_seconds}")
        else:
            settings.enable_traefik_poll = False
            logger.error(f"Traefik polling disabled: Bad url: {settings.traefik_poll_url}")

    logger.debug(f"Docker Polling Mode: {'On' if settings.enable_docker_poll else 'Off'}")
    logger.debug(f"Docker Poll Seconds: {settings.docker_timeout_seconds}")

    for dom in settings.domains:
        logger.debug(f"Domain Configuration: {dom.name}")
        logger.debug(f"  Target Domain: {dom.target_domain}")
        logger.debug(f"  TTL: {dom.ttl}")
        logger.debug(f"  Record Type: {dom.rc_type}")
        logger.debug(f"  Proxied: {dom.proxied}")
        logger.debug(f"  Excluded Subdomains: {dom.excluded_sub_domains}")

    return logger


def get_logger(settings: Settings | None = None) -> logging.Logger:
    global logger
    if logger is None and settings is None:
        raise ValueError("Logger has not been initialized")
    # Init logger if needed
    assert settings is not None, "Settings must be provided if logger is not initialized"
    logger = logger or initialize_logger(settings)
    return logger
