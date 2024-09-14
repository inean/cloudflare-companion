from functools import lru_cache
import logging
import sys

from dns_synchub.settings import Settings


@lru_cache
def console_log_handler(*, formatter: logging.Formatter) -> logging.Handler:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)
    return handler


@lru_cache
def file_log_handler(filename: str, *, formatter: logging.Formatter) -> logging.Handler:
    try:
        handler = logging.FileHandler(filename)
        handler.setFormatter(formatter)
    except OSError as err:
        logging.critical(f"Could not open log file '{err.filename}': {err.strerror}")
    return handler


# set up logging
@lru_cache
def initialize_logger(settings: Settings) -> logging.Logger:
    # Set up logging
    logger = logging.getLogger(settings.service_name)

    # remove all existing handlers, if any
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Set the log level
    logger.setLevel(settings.log_level)

    # Set up  console logging
    if 'stderr' in settings.log_handlers:
        handler = console_log_handler(formatter=settings.log_formatter)
        logger.addHandler(handler)

    # Set up file logging
    if 'file' in settings.log_handlers:
        handler = file_log_handler(settings.log_file, formatter=settings.log_formatter)
        logger.addHandler(handler)

    # Set up telemetry
    telemetry_options = {
        'use_otlp_console_handler': 'otlp_console' in settings.log_handlers,
        'use_otlp_handler': 'otlp' in settings.log_handlers,
    }
    if any(telemetry_options.values()):
        try:
            from dns_synchub.telemetry import telemetry_log_handler  # type: ignore

            handler = telemetry_log_handler(settings.service_name, **telemetry_options)
            logger.addHandler(handler)
        except ImportError:
            logger.warning('Telemetry module not found. Logging to console only.')

    return logger


def get_logger(name: str | Settings) -> logging.Logger:
    if isinstance(name, str):
        return logging.getLogger(name)
    logger = logging.getLogger(name.service_name)
    initialize_logger(name)
    return logger
