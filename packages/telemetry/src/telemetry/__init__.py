import functools
import inspect
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from types import FunctionType
from typing import (
    Any,
    ClassVar,
    Generic,
    Literal,
    TypeVar,
    cast,
    overload,
)

from opentelemetry import trace
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import Tracer
from opentelemetry.util.types import AttributeValue
from typing_extensions import override

R = TypeVar('R', bound=Any)
AR = TypeVar('AR', bound=Awaitable[Any])
F = TypeVar('F', bound=Callable[..., Any] | type)


class BaseDecorator(ABC):
    @classmethod
    def _mark(cls) -> str:
        return f'{cls.__name__.lower()}_instrumented'

    @classmethod
    def _get_mark(cls, func: Callable[..., Any]) -> bool:
        return getattr(func, cls._mark(), False)

    @classmethod
    def _set_mark(cls, func: Callable[..., Any]) -> None:
        setattr(func, cls._mark(), True)

    @classmethod
    def is_instrumented(
        cls,
        func_or_cls: Callable[..., Any] | type,
        name: str | None = None,
        descriptor: Literal['fget', 'fset', 'fdel'] = 'fget',
        *,
        mark: bool = False,
    ) -> bool:
        if name is not None:
            func_or_cls = getattr(func_or_cls, name)
        if isinstance(func_or_cls, property):
            func_or_cls = getattr(func_or_cls, descriptor)
        # unwrap the function
        unwrapped = inspect.unwrap(func_or_cls)
        # check if the function is already decorated.
        marked = cls._get_mark(unwrapped)
        if not marked and mark:
            # Mark it if needed
            cls._set_mark(unwrapped)
        return marked

    def decorate_class(self, cls: type) -> type:
        for name, method in inspect.getmembers(cls, inspect.isfunction):
            if name.startswith('_'):
                continue
            decorated = self.decorate_method(method)
            if isinstance(inspect.getattr_static(cls, name), staticmethod):
                decorated = staticmethod(decorated)
            setattr(cls, name, decorated)
        return cls

    @abstractmethod
    def decorate_method(self, func: Callable[..., R | AR]) -> Callable[..., R | AR]: ...


class InstrumentOptions(Generic[F]):
    class NamingSchemes:
        @staticmethod
        def function_qualified_name(func: F) -> str:
            return func.__qualname__

        @staticmethod
        def function_module_name(func: F) -> str:
            return func.__module__

        span_default_scheme = function_qualified_name
        tracer_default_scheme = function_module_name

    span_scheme: ClassVar[Callable[..., str]] = NamingSchemes.span_default_scheme
    tracer_scheme: ClassVar[Callable[..., str]] = NamingSchemes.tracer_default_scheme

    default_attributes: ClassVar[dict[str, AttributeValue]] = {}

    @staticmethod
    def set_naming_scheme(naming_scheme: Callable[..., str]) -> None:
        InstrumentOptions.span_scheme = naming_scheme

    @staticmethod
    def set_default_attributes(attributes: dict[str, AttributeValue]) -> None:
        assert isinstance(attributes, dict)
        InstrumentOptions.default_attributes.update(attributes)


class Instrument(BaseDecorator):
    def __init__(
        self,
        *,
        span_name: str | None = None,
        attributes: dict[str, AttributeValue] | None = None,
        record_exception: bool = True,
        tracer: Tracer | None = None,
        ignore: bool = False,
    ):
        self.span_name = span_name
        self.record_exception = record_exception
        self.attributes = attributes or {}
        self.tracer = tracer
        self.ignore = ignore

    @staticmethod
    def _semantic_attributes(func: Callable[..., Any]) -> dict[str, AttributeValue]:
        data: dict[str, AttributeValue] = {
            SpanAttributes.CODE_NAMESPACE: func.__module__,
            SpanAttributes.CODE_FUNCTION: func.__qualname__,
        }
        try:
            original_func = inspect.unwrap(func)
            # Set only if the function is defined in a file
            data[SpanAttributes.CODE_FILEPATH] = inspect.getfile(original_func)
            data[SpanAttributes.CODE_LINENO] = cast(int, original_func.__code__.co_firstlineno)
        except (AttributeError, ValueError, TypeError):
            pass
        return data

    @override
    def decorate_method(self, func: Callable[..., R | AR]) -> Callable[..., R | AR]:
        # Common code for sync and async wrappers
        name = self.span_name or InstrumentOptions.span_scheme(func)
        tracer = self.tracer or trace.get_tracer(InstrumentOptions.tracer_scheme(func))

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            with tracer.start_as_current_span(name, record_exception=self.record_exception) as span:
                span.set_attributes(self._semantic_attributes(func))
                span.set_attributes(InstrumentOptions.default_attributes)
                span.set_attributes(self.attributes)

                # Call the sync function
                return func(*args, **kwargs)

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            with tracer.start_as_current_span(name, record_exception=self.record_exception) as span:
                span.set_attributes(self._semantic_attributes(func))
                span.set_attributes(InstrumentOptions.default_attributes)
                span.set_attributes(self.attributes)

                # Call the async function
                return await cast(AR, func(*args, **kwargs))

        # Check if the function should be ignored
        if self.ignore:
            return func
        # Check if already decorated. If not, mark it
        if self.is_instrumented(func, mark=True):
            return func

        wrapper: Callable[..., R | AR] = sync_wrapper
        if inspect.iscoroutinefunction(func):
            wrapper = cast(Callable[..., AR], async_wrapper)
        if isinstance(func, FunctionType):
            setattr(wrapper, '__signature__', inspect.signature(func))
        return wrapper


@overload
def instrument() -> Callable[[F], F]: ...


@overload
def instrument(_func_or_cls: F | None = None) -> F: ...


@overload
def instrument(**kwargs: Any) -> Callable[[F], F]: ...


def instrument(_func_or_cls: F | None = None, **kwargs: Any) -> Callable[[F], F]:
    def decorate_class(cls: type) -> type:
        return Instrument(**kwargs).decorate_class(cls)

    def decorate_func(func_or_cls: F) -> F:
        return cast(F, Instrument(**kwargs).decorate_method(func_or_cls))

    def decorate_classmethod(func: F) -> F:
        return cast(F, classmethod(Instrument(**kwargs).decorate_method(inspect.unwrap(func))))

    if isinstance(_func_or_cls, type):
        # If it's a class, decorate all its methods
        return cast(F, decorate_class(_func_or_cls))
    elif isinstance(_func_or_cls, classmethod):  # type: ignore[reportUnnecessaryIsinstance]
        # If it's a class method, decorate it
        return decorate_classmethod(cast(F, _func_or_cls))
    elif callable(_func_or_cls):
        # If it's a function, decorate it
        return decorate_func(cast(F, _func_or_cls))
    else:
        # If it's a decorator without arguments, return the decorator
        assert _func_or_cls is None
        return decorate_func
