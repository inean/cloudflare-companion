import asyncio
import inspect
from collections.abc import Callable
from typing import (
    Any,
    TypeVar,
    cast,
)
from unittest.mock import patch

import pytest
from telemetry import Instrument, instrument

F = TypeVar('F', bound=Callable[..., Any] | type)

DecorateFunc = Callable[[Callable[..., Any]], Callable[..., Any]]


@pytest.fixture(params=[instrument])
def decorator(request: pytest.FixtureRequest) -> Callable[[F], F]:
    return cast(Callable[[F], F], request.param)


def test_decorator_on_function(decorator: DecorateFunc) -> None:
    @decorator
    def regular_function(x: int, y: int) -> int:
        return x + y

    assert regular_function(2, 3) == 5
    assert Instrument.is_instrumented(regular_function)


def test_decorator_on_async_function(decorator: DecorateFunc) -> None:
    @decorator
    async def async_function(x: int, y: int) -> int:
        return x * y

    result = asyncio.run(async_function(2, 3))
    assert result == 6
    assert Instrument.is_instrumented(async_function)


def test_decorator_on_static_method(decorator: DecorateFunc) -> None:
    class SampleClass:
        @decorator
        @staticmethod
        def static_method(x: int) -> int:
            return x - 1

    assert SampleClass.static_method(5) == 4
    assert Instrument.is_instrumented(SampleClass.static_method)


def test_decorator_on_class_method(decorator: DecorateFunc) -> None:
    class SampleClass:
        value = 10

        @classmethod
        @decorator
        def class_method(cls, x: int) -> int:
            return cls.value + x

    assert SampleClass.class_method(5) == 15
    assert Instrument.is_instrumented(SampleClass.class_method)


def test_class_method_decorator_with_args() -> None:
    class ClassMethodClass:
        @classmethod
        @instrument(ignore=True)
        def class_method(cls) -> str:
            return cls.__name__

    assert ClassMethodClass.class_method() == 'ClassMethodClass'
    assert not Instrument.is_instrumented(ClassMethodClass, 'class_method')

    # Inspect the signature to ensure decorators are not observed
    original_signature = inspect.signature(ClassMethodClass.class_method)
    expected_signature = inspect.signature(inspect.unwrap(ClassMethodClass.class_method))
    assert (
        original_signature == expected_signature
    ), f'Expected {expected_signature}, but got {original_signature}'


def test_decorator_on_class_method_inv(decorator: DecorateFunc) -> None:
    class SampleClass:
        value = 10

        @decorator
        @classmethod
        def class_method(cls, x: int) -> int:
            return cls.value + x

    assert SampleClass.class_method(5) == 15
    assert Instrument.is_instrumented(SampleClass.class_method)


def test_decorator_on_property_method(decorator: DecorateFunc) -> None:
    class SampleClass:
        def __init__(self, value: int):
            self._value = value

        @property
        @decorator
        def value(self) -> int:
            return self._value

    instance = SampleClass(20)
    assert instance.value == 20
    assert Instrument.is_instrumented(SampleClass, 'value', descriptor='fget')


def test_decorator_on_protected_method(decorator: DecorateFunc) -> None:
    class SampleClass:
        @decorator
        def _protected_method(self) -> int:
            return 30

    instance = SampleClass()
    assert instance._protected_method() == 30
    assert Instrument.is_instrumented(SampleClass, '_protected_method')


def test_decorator_with_ignore_option() -> None:
    @instrument(ignore=True)
    def ignored_function() -> int:
        return 100

    assert ignored_function() == 100
    assert not Instrument.is_instrumented(ignored_function)


def test_decorator_on_async_method(decorator: DecorateFunc) -> None:
    class SampleClass:
        @decorator
        async def async_method(self) -> int:
            return 50

    instance = SampleClass()
    result = asyncio.run(instance.async_method())
    assert result == 50
    assert Instrument.is_instrumented(SampleClass, 'async_method')


def test_decorator_on_already_instrumented_method(decorator: DecorateFunc) -> None:
    with patch.object(Instrument, '_set_mark', wraps=Instrument._set_mark) as mock_set_mark:

        class SampleClass:
            @decorator
            @decorator
            def method(self) -> int:
                return 42

        # Instantiate the class and call the method
        instance = SampleClass()
        assert instance.method() == 42
        assert Instrument.is_instrumented(SampleClass, 'method')

        # Assert that '_set_mark' was called only once
        mock_set_mark.assert_called_once()


def test_decorator_on_class(decorator: DecorateFunc) -> None:
    @decorator
    class InstrumentedClass:
        def a_method(self) -> int:
            return 42

        @decorator
        def an_already_instrumented_method(self) -> int:
            return 42

        def _a_protected_method(self) -> int:  # protected methods are not instrumented by default
            return 42

        @staticmethod
        def static_method() -> int:
            return 42

        @classmethod
        def class_method(cls) -> int:
            return 42

        @property  # properties are not instrumented by default
        @decorator
        def a_property(self) -> int:
            return 42

    instance = InstrumentedClass()

    assert instance.a_method() == 42
    assert instance._a_protected_method() == 42
    assert instance.an_already_instrumented_method() == 42
    assert instance.static_method() == 42
    assert InstrumentedClass.static_method() == 42
    assert instance.class_method() == 42
    assert instance.a_property == 42

    # Check if property is instrumented
    assert Instrument.is_instrumented(InstrumentedClass, 'a_property', descriptor='fget')

    # Check if methods are instrumented
    for name, _ in inspect.getmembers(InstrumentedClass, inspect.isfunction):
        if not name.startswith('_'):
            assert Instrument.is_instrumented(InstrumentedClass, name)

    # Protected methods are not instrumented by default
    assert not Instrument.is_instrumented(InstrumentedClass, '_a_protected_method')


if __name__ == '__main__':
    pytest.main(['-sv', __file__])
