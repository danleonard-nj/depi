"""
Shared fixtures for integration tests.

Every integration is exercised against the same set of services so that a
difference in results points at the adapter, not at the container.
"""

import itertools

import pytest

from depi import ServiceCollection

# Records disposal order across a test; cleared by the `services` fixture.
DISPOSED: list = []

_ids = itertools.count()


class Config:
    """Singleton: one instance for the life of the provider."""

    def __init__(self):
        self.name = 'config'


class RequestId:
    """Scoped: one instance per request, so its id identifies the scope."""

    def __init__(self):
        self.id = next(_ids)


class Ephemeral:
    """Transient: a fresh instance on every resolve."""

    def __init__(self):
        self.id = next(_ids)


class Disposable:
    """Scoped, and records disposal so teardown can be asserted on."""

    def __init__(self):
        self.id = next(_ids)
        self.disposed = False

    def dispose(self):
        self.disposed = True
        DISPOSED.append(self.id)


class Greeter:
    """Has a dependency, to prove constructor injection still runs under a scope."""

    def __init__(self, config: Config):
        self.config = config

    def greet(self):
        return f'hello from {self.config.name}'


@pytest.fixture
def services():
    DISPOSED.clear()
    collection = ServiceCollection()
    collection.add_singleton(Config)
    collection.add_scoped(RequestId)
    collection.add_scoped(Disposable)
    collection.add_transient(Ephemeral)
    collection.add_transient(Greeter)
    return collection


@pytest.fixture
def provider(services):
    return services.build_provider()
