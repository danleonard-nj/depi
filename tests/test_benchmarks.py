
import pytest
import psutil
import os
from time import perf_counter
from depi import ServiceCollection, DependencyInjector
from dependency_injector import containers, providers
from dependency_injector.wiring import Provide, inject

# Mock classes for benchmarking (same as original)


class Config:
    def __init__(self):
        self.setting = "test"


class Client:
    def __init__(self, config: Config):
        self._config = config


class Logger:
    def __init__(self):
        pass


class Cache:
    def __init__(self):
        pass


class EmailService:
    def __init__(self, config: Config, client: Client, logger: Logger, cache: Cache):
        self._config = config
        self._client = client
        self._logger = logger
        self._cache = cache

# depi setup


def setup_depi():
    services = ServiceCollection()
    services.add_singleton(Config)
    services.add_singleton(Client)
    services.add_singleton(Logger)
    services.add_singleton(Cache)
    services.add_singleton(EmailService)
    return services.build_provider()

# dependency-injector setup


class Container(containers.DeclarativeContainer):
    config = providers.Singleton(Config)
    client = providers.Singleton(Client, config=config)
    logger = providers.Singleton(Logger)
    cache = providers.Singleton(Cache)
    email_service = providers.Singleton(EmailService, config=config, client=client, logger=logger, cache=cache)

# Benchmark resolution time


def test_depi_resolution(benchmark):
    provider = setup_depi()
    benchmark.pedantic(provider.resolve, args=(EmailService,), rounds=500000, iterations=1)


def test_di_resolution(benchmark):
    container = Container()
    benchmark.pedantic(container.email_service, rounds=500000, iterations=1)

# Benchmark memory usage (improved approach)


def test_depi_memory(benchmark):
    import gc
    provider = setup_depi()

    def memory_intensive_resolve():
        # Create multiple instances to better measure memory impact
        instances = []
        for _ in range(100):
            instances.append(provider.resolve(EmailService))
        return instances

    # Force garbage collection before measurement
    gc.collect()
    process = psutil.Process(os.getpid())
    mem_before = process.memory_info().rss

    result = benchmark.pedantic(memory_intensive_resolve, rounds=10, iterations=1)

    gc.collect()
    mem_after = process.memory_info().rss
    mem_used = (mem_after - mem_before) / 1024 / 1024  # Convert to MB
    benchmark.extra_info['memory_mb'] = mem_used
    return mem_used


def test_di_memory(benchmark):
    import gc
    container = Container()

    def memory_intensive_resolve():
        # Create multiple instances to better measure memory impact
        instances = []
        for _ in range(100):
            instances.append(container.email_service())
        return instances

    # Force garbage collection before measurement
    gc.collect()
    process = psutil.Process(os.getpid())
    mem_before = process.memory_info().rss

    result = benchmark.pedantic(memory_intensive_resolve, rounds=10, iterations=1)

    gc.collect()
    mem_after = process.memory_info().rss
    mem_used = (mem_after - mem_before) / 1024 / 1024  # Convert to MB
    benchmark.extra_info['memory_mb'] = mem_used
    return mem_used


# Benchmark setup overhead
def test_depi_setup(benchmark):
    benchmark(setup_depi)


def test_di_setup(benchmark):
    benchmark(lambda: Container())


# Benchmark with complex dependency graph
class DatabaseService:
    def __init__(self, config: Config, logger: Logger):
        self._config = config
        self._logger = logger


class NotificationService:
    def __init__(self, email: EmailService, db: DatabaseService, cache: Cache):
        self._email = email
        self._db = db
        self._cache = cache


def setup_depi_complex():
    services = ServiceCollection()
    services.add_singleton(Config)
    services.add_singleton(Client)
    services.add_singleton(Logger)
    services.add_singleton(Cache)
    services.add_singleton(EmailService)
    services.add_singleton(DatabaseService)
    services.add_singleton(NotificationService)
    return services.build_provider()


class ComplexContainer(containers.DeclarativeContainer):
    config = providers.Singleton(Config)
    client = providers.Singleton(Client, config=config)
    logger = providers.Singleton(Logger)
    cache = providers.Singleton(Cache)
    email_service = providers.Singleton(EmailService, config=config, client=client, logger=logger, cache=cache)
    database_service = providers.Singleton(DatabaseService, config=config, logger=logger)
    notification_service = providers.Singleton(NotificationService, email=email_service, db=database_service, cache=cache)


def test_depi_complex_resolution(benchmark):
    provider = setup_depi_complex()
    benchmark.pedantic(provider.resolve, args=(NotificationService,), rounds=100000, iterations=1)


def test_di_complex_resolution(benchmark):
    container = ComplexContainer()
    benchmark.pedantic(container.notification_service, rounds=100000, iterations=1)
