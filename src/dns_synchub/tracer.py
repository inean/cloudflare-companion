import importlib
import os
from sys import stderr
from typing import (
    Any,
    Optional,
)

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)
from opentelemetry.trace import SpanKind, Tracer
from opentelemetry.trace.span import Span
from opentelemetry.trace.status import StatusCode

from dns_synchub.telemetry import (
    TelementryExporters as Exporters,
    TelemetryEnv as Env,
    TelemetryEnvDefaults as Constants,
)
from dns_synchub.utils._once import Once


class _TelemetryTracer:
    _instance: Optional['_TelemetryTracer'] = None
    _set_once = Once()

    def __init__(self, service_name: str | None = None, exporters: set[str] | None = None):
        if service_name is None:
            service_name = os.environ.get(
                Env.OTEL_SERVICE_NAME,
                Constants.OTEL_SERVICE_NAME,
            )
        if exporters is None:
            exporters = set(
                os.environ.get(
                    Env.OTEL_TRACES_EXPORTER,
                    Constants.OTEL_TRACES_EXPORTER,
                ).split(',')
            )

        self.service_name = service_name
        self.exporters = exporters
        self._tracer_provider = self._init_tracer_provider()

    def _init_tracer_provider(self) -> TracerProvider:
        # Create a tracer provider
        tracer_provider = TracerProvider(
            resource=Resource.create({
                'service.name': self.service_name,
            })
        )
        # Console span exporter
        if Exporters.CONSOLE in self.exporters:
            console_exporter = ConsoleSpanExporter(out=stderr)
            span_processor = BatchSpanProcessor(console_exporter)
            tracer_provider.add_span_processor(span_processor)

        # OTLP span exporter
        if Exporters.OTLP in self.exporters:
            otlp_modname = 'opentelemetry.exporter.otlp.proto.grpc.trace_exporter'
            if Env.OTEL_EXPORTER_OTLP_ENDPOINT not in os.environ:
                raise ValueError(f'{Env.OTEL_EXPORTER_OTLP_ENDPOINT} environment variable not set')
            try:
                otlp_exporter = importlib.import_module(otlp_modname)
            except ImportError as err:
                raise ImportError(
                    f'Missing "opentelemetry-exporter-otlp-proto-grpc" package. '
                    f'Use [otlp] optional feature or remove "{Exporters.OTLP}" '
                    f'from "{Env.OTEL_TRACES_EXPORTER}"'
                ) from err
            span_processor = BatchSpanProcessor(otlp_exporter.OTLPSpanExporter(insecure=True))
            tracer_provider.add_span_processor(span_processor)

        return tracer_provider

    def get_tracer(self, name: str = __name__, **kwargs: Any) -> Tracer:
        return self.tracer_provider.get_tracer(name, **kwargs)

    @property
    def tracer_provider(self) -> TracerProvider:
        assert self._tracer_provider is not None
        return self._tracer_provider


def telemetry_tracer(
    service_name: str | None = None, exporters: set[str] | None = None
) -> _TelemetryTracer:
    def set_tp() -> None:
        _TelemetryTracer._instance = _TelemetryTracer(service_name, exporters)
        trace.set_tracer_provider(_TelemetryTracer._instance.tracer_provider)

    executed = _TelemetryTracer._set_once.do_once(set_tp)
    if service_name is not None and executed is False:
        raise RuntimeError('Overriding of current TracerProvider is not allowed')

    assert _TelemetryTracer._instance is not None
    return _TelemetryTracer._instance


def get_tracer(
    instrumenting_module_name: str,
    instrumenting_library_version: str | None = None,
    tracer_provider: TracerProvider | None = None,
    schema_url: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> Tracer:
    tracer_factory = tracer_provider or telemetry_tracer()
    return tracer_factory.get_tracer(
        instrumenting_module_name,
        instrumenting_library_version=instrumenting_library_version,
        schema_url=schema_url,
        attributes=attributes,
    )


__all__ = [
    'telemetry_tracer',
    'get_tracer',
    'StatusCode',
    'Span',
    'SpanKind',
]


def __dir__() -> list[str]:
    return sorted(__all__)
