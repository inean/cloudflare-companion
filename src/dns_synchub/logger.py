import importlib
import logging
import os
import sys
from functools import partial
from typing import Protocol, cast

from dns_synchub.settings import Settings
from dns_synchub.telemetry import (
    TelementryExporters as Exporters,
    TelemetryEnv as Envs,
    TelemetryEnvDefaults as Constants,
)
from dns_synchub.types import LogHandlerType
from dns_synchub.utils._once import Once


def _telemetry_logger(service_name: str, *, exporters: set[str] | None = None) -> logging.Handler:
    try:
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, ConsoleLogExporter
        from opentelemetry.sdk.resources import Resource
    except ImportError:
        return logging.NullHandler()

    if exporters is None:
        exporters = set(
            os.environ.get(
                Envs.OTEL_LOGGER_EXPORTER,
                Constants.OTEL_LOGGER_EXPORTER,
            ).split(',')
        )

    # Set up a logging provider
    logger_provider = LoggerProvider(
        resource=Resource.create({
            'service.name': service_name,
        })
    )

    # Configure ConsoleLogExporter
    if Exporters.CONSOLE in exporters:
        term_exporter = ConsoleLogExporter(out=sys.stderr)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(term_exporter))

    # Configure OTLPLogExporter
    if Exporters.OTLP in exporters:
        otlp_modname = 'opentelemetry.exporter.otlp.proto.grpc._log_exporter'
        if Envs.OTEL_EXPORTER_OTLP_ENDPOINT not in os.environ:
            raise ValueError(f'{Envs.OTEL_EXPORTER_OTLP_ENDPOINT} environment variable not set')
        try:
            otlp_exporter = importlib.import_module(otlp_modname)
        except ImportError as err:
            raise ImportError(
                f'Missing "opentelemetry-exporter-otlp-proto-grpc" package. '
                f'Use [otlp] optional feature or remove "{Exporters.OTLP}" '
                f'from "{Envs.OTEL_LOGGER_EXPORTER}"'
            ) from err
        batch_processor = BatchLogRecordProcessor(otlp_exporter.OTLPLogExporter(insecure=True))
        logger_provider.add_log_record_processor(batch_processor)

    # Set up a logging handler for standard Python logging
    set_logger_provider(logger_provider)
    return LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)


def _console_log_handler(console: str, *, formatter: logging.Formatter) -> logging.Handler:
    match console:
        case 'stdout':
            handler = logging.StreamHandler(sys.stdout)
        case 'stderr':
            handler = logging.StreamHandler(sys.stderr)
        case _:
            raise ValueError(f'Invalid console log handler: {console}')
    handler.setFormatter(formatter)
    return handler


def _file_log_handler(filename: str, *, formatter: logging.Formatter) -> logging.Handler:
    try:
        handler = logging.FileHandler(filename)
        handler.setFormatter(formatter)
    except OSError as err:
        raise RuntimeError(f"Could not open log file '{err.filename}': {err.strerror}") from err
    return handler


def initialize_logger(logger: logging.Logger, *, settings: Settings) -> logging.Logger:
    # remove all existing handlers, if any
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Set the log level
    logger.setLevel(settings.log_level)

    # Set up  console logging
    if LogHandlerType.STDOUT in settings.log_handlers:
        handler = _console_log_handler(settings.log_console, formatter=settings.log_formatter)
        logger.addHandler(handler)

    # Set up file logging
    if LogHandlerType.FILE in settings.log_handlers:
        handler = _file_log_handler(settings.log_file, formatter=settings.log_formatter)
        logger.addHandler(handler)

    # Set up telemetry
    handler = _telemetry_logger(settings.service_name)
    if not isinstance(handler, logging.NullHandler):
        logger.addHandler(handler)

    # Set up the logger
    return logger


class InitializeLoggerProtocol(Protocol):
    def __call__(self, logger: logging.Logger, *, settings: Settings) -> logging.Logger: ...


_logger_once = Once()


def set_default_logger(
    logger: logging.Logger,
    *,
    settings: Settings,
    setup_func: InitializeLoggerProtocol | None = None,
) -> logging.Logger:
    global _logger_once

    setup_func = setup_func or initialize_logger
    if _logger_once.do_once(partial(setup_func, logger, settings=settings)) is False:
        get_default_logger().info('Logger Already initialized')
    return get_default_logger()


def get_default_logger() -> logging.Logger:
    return cast(logging.Logger, _logger_once.result)
