import os
from sys import stderr
from typing import TYPE_CHECKING, Literal

try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.trace import Tracer

    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    if not TYPE_CHECKING:

        class Tracer: ...

        # Default no-op implementations in case OpenTelemetry is not available
        class NoOpTracer(Tracer):
            def start_as_current_span(self, name: str) -> 'NoOpTracer':
                return self

            def __enter__(self) -> 'NoOpTracer':
                return self

            def __exit__(
                self,
                exc_type: type[BaseException] | None,
                exc_val: BaseException | None,
                exc_tb: type[BaseException] | None,
            ) -> None:
                pass

            def add_event(self, name: str) -> None:
                pass

    OPENTELEMETRY_AVAILABLE = False


class TelemetryTracer:
    has_run: bool = False

    def __init__(self, service_name: str, exporters: set[Literal['console', 'otlp']]):
        self.exporters = exporters
        self.service_name = service_name

        if OPENTELEMETRY_AVAILABLE and not self.has_run:
            self._init_tracer()

    def _init_tracer(self) -> None:
        # Create a tracer provider
        tracer_provider = TracerProvider(
            resource=Resource.create({
                'service.name': self.service_name,
            })
        )
        # Console span exporter
        if 'console' in self.exporters:
            console_exporter = ConsoleSpanExporter(out=stderr)
            span_processor = BatchSpanProcessor(console_exporter)
            tracer_provider.add_span_processor(span_processor)

        # OTLP span exporter
        if 'otlp' in self.exporters:
            if 'OTEL_EXPORTER_OTLP_ENDPOINT' not in os.environ:
                raise ValueError('OTEL_EXPORTER_OTLP_ENDPOINT environment variable not set')

            otlp_exporter = OTLPSpanExporter(insecure=True)
            span_processor = BatchSpanProcessor(otlp_exporter)
            tracer_provider.add_span_processor(span_processor)

        # Set the global tracer provider
        trace.set_tracer_provider(tracer_provider)

    def get_tracer(self, name: str = __name__) -> Tracer:
        if not OPENTELEMETRY_AVAILABLE:
            if not TYPE_CHECKING:
                return NoOpTracer()
        return trace.get_tracer_provider().get_tracer(name)


def telemetry_tracer(
    service_name: str, exporters: set[Literal['console', 'otlp']]
) -> TelemetryTracer:
    return TelemetryTracer(service_name, exporters)
