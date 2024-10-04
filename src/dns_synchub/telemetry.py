# Environment variables
class TelemetryEnv:
    OTEL_SERVICE_NAME = 'OTEL_SERVICE_NAME'
    OTEL_LOGGER_EXPORTER = 'OTEL_LOGGER_EXPORTER'
    OTEL_METRICS_EXPORTER = 'OTEL_METRICS_EXPORTER'
    OTEL_TRACES_EXPORTER = 'OTEL_TRACES_EXPORTER'
    OTEL_EXPORTER_OTLP_ENDPOINT = 'OTEL_EXPORTER_OTLP_ENDPOINT'


class TelementryExporters:
    CONSOLE = 'console'
    NONE = 'none'
    OTLP = 'otlp'
    PROMETHEUS = 'prometheus'


# Default Environment values
class TelemetryEnvDefaults:
    OTEL_SERVICE_NAME = 'dns-synchub'
    OTEL_TRACES_EXPORTER = 'otlp'
    OTEL_LOGGER_EXPORTER = 'otlp'
    OTEL_METRICS_EXPORTER = 'otlp'


# Attributes
class TelemetrySpans:
    POLLER_START = 'poller.start'
    POLLER_STOP = 'poller.stop'
    ASYNCIO_CANCEL = 'asyncio.cancel'
    EVENTS_EMIT = 'events.emit'
    MAPPERS_CALL = 'mappers.run'
    CLOUDFLARE_GET = 'mappers.cloudflare.get'
    CLOUDFLARE_POST = 'mappers.cloudflare.post'
    CLOUDFLARE_PUT = 'mappers.cloudflare.put'
    CLOUDFLARE_SYNC = 'mappers.cloudflare.sync'


class TelemetryAttributes:
    EVENT_CLASS = 'event.class'
    EVENT_ORIGIN = 'event.origin'
    EVENT_HOSTS = 'event.hosts'
    POLLER_CLASS = 'poller.class'
    STATE_CANCELLED = 'state.cancelled'
    STATE_RUNNING = 'state.running'
    TIMEOUT_REACHED = 'timeout.reached'
    TIMEOUT_STOP_AT = 'timeout.stop_at'
    TIMEOUT_VALUE = 'timeout.value'
    MAPPER_CLASS = 'mapper.class'


class TelemetryConstants:
    TIMEOUT_ENDLESS = 'endless'
