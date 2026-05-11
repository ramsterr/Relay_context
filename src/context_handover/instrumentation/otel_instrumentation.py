from __future__ import annotations
from typing import Optional
import logging

logger = logging.getLogger(__name__)

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.jaeger.thrift import JaegerExporter
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    logger.warning("opentelemetry not available")


class ContextInstrumentor:
    def __init__(
        self,
        service_name: str = "context-handover",
        jaeger_endpoint: Optional[str] = None,
    ):
        if not OTEL_AVAILABLE:
            self.tracer = None
            return

        resource = Resource.create({SERVICE_NAME: service_name})
        provider = TracerProvider(resource=resource)

        if jaeger_endpoint:
            jaeger_exporter = JaegerExporter(
                endpoint=jaeger_endpoint,
                insecure=True,
            )
            provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))

        trace.set_tracer_provider(provider)
        self.tracer = trace.get_tracer(__name__)

        logger.info(f"OTEL instrumentation initialized: {service_name}")

    def start_span(self, name: str, **attributes):
        if not self.tracer:
            return NoOpSpan()
        return self.tracer.start_span(name, attributes=attributes)

    def trace_extraction(self, session_id: str, atom_count: int):
        with self.start_span("atom_extraction", session_id=session_id) as span:
            span.set_attribute("atom_count", atom_count)

    def trace_checkpoint(
        self,
        session_id: str,
        checkpoint_id: str,
        level: str,
        atom_count: int,
    ):
        with self.start_span("checkpoint", session_id=session_id) as span:
            span.set_attribute("checkpoint_id", checkpoint_id)
            span.set_attribute("level", level)
            span.set_attribute("atom_count", atom_count)

    def trace_handover(
        self,
        session_from: str,
        session_to: str,
        atom_count: int,
        drift_score: Optional[float] = None,
    ):
        with self.start_span("handover", session_from=session_from) as span:
            span.set_attribute("session_to", session_to)
            span.set_attribute("atom_count", atom_count)
            if drift_score is not None:
                span.set_attribute("drift_score", drift_score)

    def trace_drift_measurement(
        self,
        session_id: str,
        kl_structural: float,
        jaccard: float,
        composite: float,
    ):
        with self.start_span("drift_measurement", session_id=session_id) as span:
            span.set_attribute("kl_structural", kl_structural)
            span.set_attribute("jaccard", jaccard)
            span.set_attribute("composite", composite)


class NoOpSpan:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def set_attribute(self, key: str, value):
        pass


class MetricsCollector:
    def __init__(self):
        self.counters: dict = {}
        self.gauges: dict = {}

    def increment(self, name: str, value: int = 1, **labels):
        key = (name, tuple(sorted(labels.items())))
        self.counters[key] = self.counters.get(key, 0) + value

    def gauge(self, name: str, value: float, **labels):
        key = (name, tuple(sorted(labels.items())))
        self.gauges[key] = value

    def get_metric(self, name: str) -> dict:
        result = {}
        for (metric_name, labels), value in {**self.counters, **self.gauges}.items():
            if metric_name == name:
                result[str(labels)] = value
        return result

    def reset(self):
        self.counters.clear()
        self.gauges.clear()