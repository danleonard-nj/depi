"""
Thread safety and high-concurrency tests for depi injectors.

Covers:
- Singleton creation under concurrent threads (created exactly once)
- Transient uniqueness under concurrent threads (new instance per call)
- Scoped isolation across threads (each thread's scope is independent)
- Concurrent scope creation/disposal
- FastAPI: ContextVar-based scope isolation under concurrent async requests
- FastAPI: singleton sharing across concurrent requests
- Async: concurrent asyncio tasks resolve singletons safely
"""

import asyncio
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
import pytest
from fastapi import FastAPI

from depi.services import ServiceCollection, ServiceProvider, ServiceScope
from depi.injectors import FastAPIInjector, FlaskInjector, create_fastapi_injector


# ---------------------------------------------------------------------------
# Shared test services
# ---------------------------------------------------------------------------

class CountingService:
    """Tracks how many times it has been instantiated."""
    instance_count = 0
    _lock = threading.Lock()

    def __init__(self):
        with CountingService._lock:
            CountingService.instance_count += 1
        self.id = uuid.uuid4()

    @classmethod
    def reset(cls):
        with cls._lock:
            cls.instance_count = 0


class ScopedCounter:
    """Scoped service with a unique id per instance."""
    def __init__(self):
        self.id = uuid.uuid4()


class DependentService:
    def __init__(self, counter: CountingService):
        self.counter = counter
        self.id = uuid.uuid4()


def _build_provider(*, singleton=False, scoped=False, transient=False):
    services = ServiceCollection()
    CountingService.reset()
    if singleton:
        services.add_singleton(CountingService)
    if scoped:
        services.add_scoped(ScopedCounter)
    if transient:
        services.add_transient(CountingService)
    return services.build_provider()


# ---------------------------------------------------------------------------
# 1. Singleton: created exactly once under high thread concurrency
# ---------------------------------------------------------------------------

def test_singleton_created_once_under_concurrent_threads():
    """All threads racing to resolve a singleton receive the same instance."""
    N = 50
    provider = _build_provider(singleton=True)

    instances = []
    barrier = threading.Barrier(N)

    def resolve():
        barrier.wait()  # synchronise all threads to maximise race
        return provider.resolve(CountingService)

    with ThreadPoolExecutor(max_workers=N) as pool:
        futures = [pool.submit(resolve) for _ in range(N)]
        instances = [f.result() for f in as_completed(futures)]

    assert CountingService.instance_count == 1
    first = instances[0]
    assert all(inst is first for inst in instances), "All threads must share the same singleton"


def test_singleton_same_identity_across_threads():
    """Singleton resolved repeatedly from multiple threads always gives the same id."""
    provider = _build_provider(singleton=True)
    ids = set()
    lock = threading.Lock()

    def resolve_many():
        for _ in range(20):
            svc = provider.resolve(CountingService)
            with lock:
                ids.add(svc.id)

    threads = [threading.Thread(target=resolve_many) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(ids) == 1, "Singleton must always return the same id across all threads"


# ---------------------------------------------------------------------------
# 2. Transient: distinct instances under concurrent threads
# ---------------------------------------------------------------------------

def test_transient_unique_instances_under_concurrent_threads():
    """Each transient resolution from any thread produces a distinct instance."""
    provider = _build_provider(transient=True)
    ids: list[uuid.UUID] = []
    lock = threading.Lock()

    def resolve_many():
        local_ids = [provider.resolve(CountingService).id for _ in range(10)]
        with lock:
            ids.extend(local_ids)

    threads = [threading.Thread(target=resolve_many) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(ids) == len(set(ids)), "Every transient resolution must yield a unique instance"


# ---------------------------------------------------------------------------
# 3. Scoped: each scope is fully isolated, even under concurrent threads
# ---------------------------------------------------------------------------

def test_scoped_isolation_across_threads():
    """Each thread's scope holds its own independent scoped service instance."""
    services = ServiceCollection()
    services.add_scoped(ScopedCounter)
    provider = services.build_provider()

    scope_ids: list[uuid.UUID] = []
    lock = threading.Lock()

    def work():
        with provider.create_scope() as scope:
            a = scope.resolve(ScopedCounter)
            b = scope.resolve(ScopedCounter)
            assert a is b, "Same scope must return same scoped instance"
            with lock:
                scope_ids.append(a.id)

    threads = [threading.Thread(target=work) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(scope_ids) == 20
    assert len(set(scope_ids)) == 20, "Each thread's scope must hold a distinct scoped instance"


def test_scoped_does_not_bleed_across_concurrent_scopes():
    """Resolving in one scope never returns an instance from another scope."""
    services = ServiceCollection()
    services.add_scoped(ScopedCounter)
    provider = services.build_provider()

    results: dict[int, uuid.UUID] = {}
    lock = threading.Lock()

    def work(thread_idx: int):
        with provider.create_scope() as scope:
            svc = scope.resolve(ScopedCounter)
            time.sleep(0.01)  # hold scope open to increase overlap
            with lock:
                results[thread_idx] = svc.id

    threads = [threading.Thread(target=work, args=(i,)) for i in range(15)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    all_ids = list(results.values())
    assert len(all_ids) == len(set(all_ids)), "Scoped instances must not leak between concurrent scopes"


# ---------------------------------------------------------------------------
# 4. Concurrent scope creation and disposal
# ---------------------------------------------------------------------------

def test_concurrent_scope_creation_and_disposal():
    """Rapidly creating and disposing scopes from many threads must not raise."""
    services = ServiceCollection()
    services.add_singleton(CountingService)
    services.add_scoped(ScopedCounter)
    provider = services.build_provider()
    errors: list[Exception] = []
    lock = threading.Lock()

    def work():
        try:
            for _ in range(10):
                with provider.create_scope() as scope:
                    scope.resolve(CountingService)
                    scope.resolve(ScopedCounter)
        except Exception as e:
            with lock:
                errors.append(e)

    threads = [threading.Thread(target=work) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Unexpected errors during concurrent scope use: {errors}"


# ---------------------------------------------------------------------------
# 5. Async: concurrent asyncio tasks resolve singletons exactly once
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_async_singleton_created_once_under_concurrent_tasks():
    """Concurrent asyncio tasks racing to resolve a singleton get the same instance."""
    services = ServiceCollection()
    CountingService.reset()
    services.add_singleton(CountingService)
    provider = services.build_provider()

    async def resolve():
        return provider.resolve(CountingService)

    instances = await asyncio.gather(*[resolve() for _ in range(50)])

    assert CountingService.instance_count == 1
    first = instances[0]
    assert all(inst is first for inst in instances)


@pytest.mark.asyncio
async def test_async_scoped_isolation_across_tasks():
    """Each asyncio task uses its own scope and gets a distinct scoped instance."""
    services = ServiceCollection()
    services.add_scoped(ScopedCounter)
    provider = services.build_provider()

    async def work():
        with provider.create_scope() as scope:
            return scope.resolve(ScopedCounter).id

    ids = await asyncio.gather(*[work() for _ in range(30)])
    assert len(set(ids)) == 30, "Each async task scope must yield a distinct scoped instance"


# ---------------------------------------------------------------------------
# 6. FastAPI: concurrent requests – ContextVar scope isolation
# ---------------------------------------------------------------------------

def _build_fastapi_app():
    """Build a minimal FastAPI app wired with the FastAPI injector."""
    app = FastAPI()
    services = ServiceCollection()
    CountingService.reset()
    services.add_singleton(CountingService)
    services.add_scoped(ScopedCounter)
    provider = services.build_provider()

    injector = FastAPIInjector(provider)
    injector.setup(app)

    @app.get("/singleton-id")
    async def get_singleton_id():
        scope = injector.get_provider()
        # Singleton is resolved via the provider inside the scope
        svc = provider.resolve(CountingService)
        return {"singleton_id": str(svc.id)}

    @app.get("/scoped-id")
    async def get_scoped_id():
        scope = injector.get_provider()
        svc = scope.resolve(ScopedCounter)
        return {"scoped_id": str(svc.id)}

    return app, provider


@pytest.mark.asyncio
async def test_fastapi_concurrent_requests_have_isolated_scopes():
    """Each concurrent FastAPI request must produce a distinct scoped service id."""
    N = 30
    app, _ = _build_fastapi_app()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        responses = await asyncio.gather(*[client.get("/scoped-id") for _ in range(N)])

    assert all(r.status_code == 200 for r in responses)
    scoped_ids = [r.json()["scoped_id"] for r in responses]
    assert len(set(scoped_ids)) == N, "Every concurrent request must get its own scoped instance"


@pytest.mark.asyncio
async def test_fastapi_concurrent_requests_share_singleton():
    """All concurrent FastAPI requests must resolve the same singleton instance."""
    N = 30
    app, _ = _build_fastapi_app()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        responses = await asyncio.gather(*[client.get("/singleton-id") for _ in range(N)])

    assert all(r.status_code == 200 for r in responses)
    singleton_ids = {r.json()["singleton_id"] for r in responses}
    assert len(singleton_ids) == 1, "All requests must share the same singleton id"
    assert CountingService.instance_count == 1


@pytest.mark.asyncio
async def test_fastapi_contextvar_does_not_leak_scope_between_requests():
    """Ensure that ContextVar tokens are properly reset so scopes never leak."""
    from depi.injectors import _current_scope

    app = FastAPI()
    services = ServiceCollection()
    services.add_scoped(ScopedCounter)
    provider = services.build_provider()

    injector = FastAPIInjector(provider)
    injector.setup(app)

    scope_ids_seen: list[str] = []

    @app.get("/check")
    async def check():
        scope = injector.get_provider()
        svc = scope.resolve(ScopedCounter)
        return {"scope_id": str(svc.id)}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        responses = await asyncio.gather(*[client.get("/check") for _ in range(20)])

    ids = [r.json()["scope_id"] for r in responses]
    # All ids must be unique – none leaked from a previous request
    assert len(set(ids)) == 20

    # After all requests the ContextVar must be unset (reset by middleware)
    assert _current_scope.get() is None


# ---------------------------------------------------------------------------
# 7. Flask: concurrent threaded requests have isolated scopes
# ---------------------------------------------------------------------------

def test_flask_concurrent_requests_have_isolated_scopes():
    """Under Flask's threaded test mode each request must get its own scoped service."""
    try:
        from flask import Flask, jsonify
    except ImportError:
        pytest.skip("Flask not installed")

    app = Flask(__name__)
    services = ServiceCollection()
    services.add_singleton(CountingService)
    services.add_scoped(ScopedCounter)
    provider = services.build_provider()

    injector = FlaskInjector(provider)
    injector.setup(app)

    @app.get("/scoped-id")
    def get_scoped_id():
        from depi.injectors import _current_scope
        scope = _current_scope.get()
        svc = scope.resolve(ScopedCounter)
        return jsonify({"scoped_id": str(svc.id)})

    scoped_ids: list[str] = []
    lock = threading.Lock()
    errors: list[Exception] = []

    def make_request():
        try:
            with app.test_client() as client:
                r = client.get("/scoped-id")
                assert r.status_code == 200
                with lock:
                    scoped_ids.append(r.json["scoped_id"])
        except Exception as e:
            with lock:
                errors.append(e)

    threads = [threading.Thread(target=make_request) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Errors during concurrent Flask requests: {errors}"
    assert len(scoped_ids) == 20
    assert len(set(scoped_ids)) == 20, "Each Flask request must get its own scoped instance"


# ---------------------------------------------------------------------------
# 8. High-volume stress: no corruption under repeated singleton resolution
# ---------------------------------------------------------------------------

def test_high_volume_singleton_resolution_no_corruption():
    """A very high number of concurrent resolutions must not corrupt singleton state."""
    N_THREADS = 100
    N_RESOLUTIONS = 50
    provider = _build_provider(singleton=True)

    ids = set()
    lock = threading.Lock()

    def resolve_batch():
        batch = {provider.resolve(CountingService).id for _ in range(N_RESOLUTIONS)}
        with lock:
            ids.update(batch)

    with ThreadPoolExecutor(max_workers=N_THREADS) as pool:
        list(pool.map(lambda _: resolve_batch(), range(N_THREADS)))

    assert len(ids) == 1, "Singleton id must be consistent under high-volume concurrent access"
    assert CountingService.instance_count == 1
