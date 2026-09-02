"""
Tests for the ambient scope primitive.

This moved out of the old injectors module into core so that every integration
binds and reads the same contextvar; these tests pin that behaviour down
independently of any web framework.
"""

import asyncio
import threading

import pytest

from depi import (
    NoActiveScopeError,
    ServiceCollection,
    current_scope,
    get_current_scope,
    reset_current_scope,
    set_current_scope,
    use_scope,
)


class Thing:
    def __init__(self):
        self.value = 'thing'


@pytest.fixture
def provider():
    collection = ServiceCollection()
    collection.add_scoped(Thing)
    return collection.build_provider()


def test_no_scope_bound_by_default():
    assert get_current_scope() is None


def test_current_scope_raises_when_unbound():
    with pytest.raises(NoActiveScopeError):
        current_scope()


def test_no_active_scope_error_is_a_runtime_error():
    """Existing `except RuntimeError` handlers must keep working."""
    assert issubclass(NoActiveScopeError, RuntimeError)


def test_set_and_reset_round_trip(provider):
    scope = provider.create_scope()
    token = set_current_scope(scope)
    try:
        assert current_scope() is scope
    finally:
        reset_current_scope(token)
    assert get_current_scope() is None


def test_use_scope_restores_the_previous_scope(provider):
    outer = provider.create_scope()
    inner = provider.create_scope()

    with use_scope(outer):
        assert current_scope() is outer
        with use_scope(inner):
            assert current_scope() is inner
        assert current_scope() is outer

    assert get_current_scope() is None


def test_use_scope_restores_on_exception(provider):
    scope = provider.create_scope()
    with pytest.raises(ValueError):
        with use_scope(scope):
            raise ValueError('boom')
    assert get_current_scope() is None


def test_use_scope_does_not_dispose(provider):
    """Binding and lifetime are separate concerns; disposal stays with the owner."""
    scope = provider.create_scope()
    with use_scope(scope):
        thing = scope.resolve(Thing)
    assert scope.resolve(Thing) is thing


def test_scope_is_isolated_between_threads(provider):
    scope = provider.create_scope()
    seen = {}

    def worker():
        seen['scope'] = get_current_scope()

    with use_scope(scope):
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()

    assert seen['scope'] is None


@pytest.mark.asyncio
async def test_scope_is_isolated_between_tasks(provider):
    scope = provider.create_scope()
    seen = {}

    async def task():
        seen['scope'] = get_current_scope()

    with use_scope(scope):
        # A task copies the context at creation, so it sees the scope...
        await asyncio.create_task(task())
        assert seen['scope'] is scope

    async def after():
        seen['scope'] = get_current_scope()

    # ...and a task created after the bind is released does not.
    await asyncio.create_task(after())
    assert seen['scope'] is None
