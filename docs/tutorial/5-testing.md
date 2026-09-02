# 5. Tests

> File: `tests/test_shortlinks.py`

[Step 2](2-the-service.md) tested `CreateLink` by constructing it directly. This
step tests the wired application — real `CreateLink`, real `FollowLink`, real
repository logic — with the two dependencies a test wants to control replaced:
the code generator (so codes are predictable) and the store (so each test
starts empty).

## A test container

```python
# tests/test_shortlinks.py
import pytest

from depi import ServiceCollection

from shortlinks.domain import Clock, CodeGenerator, LinkRepository
from shortlinks.infrastructure import LinkStore, SqlLikeLinkRepository
from shortlinks.service import CreateLink, FollowLink, UnknownCode


class SequenceCodes:
    def __init__(self, *codes):
        self._it = iter(codes)
    def next(self):
        return next(self._it)


class FixedClock:
    def now_iso(self):
        return "2020-01-01T00:00:00+00:00"


def build_test_provider(*codes):
    services = ServiceCollection()

    services.add_singleton(LinkStore)
    services.add_singleton(Clock, instance=FixedClock())
    services.add_singleton(CodeGenerator, instance=SequenceCodes(*codes))

    services.add_scoped(LinkRepository, SqlLikeLinkRepository)   # the real one
    services.add_transient(CreateLink)                          # the real one
    services.add_transient(FollowLink)

    return services.build_provider()
```

The scoped `SqlLikeLinkRepository` and the transient use cases are the
production classes. Only `CodeGenerator` and `Clock` are swapped, via
`instance=`.

## Request-level tests

```python
def test_create_then_follow_across_scopes():
    provider = build_test_provider("aaaaaa", "bbbbbb")

    with provider.create_scope() as scope:
        link = scope.resolve(CreateLink)("https://example.com")
        assert link.code == "aaaaaa"
    # scope disposed -> repository flushed to the store

    with provider.create_scope() as scope:
        assert scope.resolve(FollowLink)("aaaaaa") == "https://example.com"


def test_hit_is_recorded():
    provider = build_test_provider("aaaaaa")
    with provider.create_scope() as scope:
        scope.resolve(CreateLink)("https://example.com")
    with provider.create_scope() as scope:
        scope.resolve(FollowLink)("aaaaaa")

    store = provider.resolve(LinkStore)
    assert store.get("aaaaaa").hits == 1


def test_unknown_code():
    provider = build_test_provider()
    with provider.create_scope() as scope:
        with pytest.raises(UnknownCode):
            scope.resolve(FollowLink)("missing")
```

Each `build_test_provider()` call builds a fresh provider, so a fresh
`LinkStore`. The tests use real scopes — the flush on `dispose()` is part of
what is being tested.

## Testing the HTTP layer

The Flask app runs under its test client with no server:

```python
from shortlinks.web_flask import create_app


def test_flask_roundtrip():
    client = create_app().test_client()

    created = client.post("/links", json={"target": "https://example.com"})
    assert created.status_code == 201

    followed = client.get(f"/{created.get_json()['code']}")
    assert followed.status_code == 302
    assert followed.headers["location"] == "https://example.com"
```

This uses the real `build_provider()`. To run the HTTP layer against the test
container instead, have `create_app()` take a provider argument
(`create_app(provider=build_test_provider(...))`) rather than calling
`build_provider()` itself.

A view wrapped with `@injector.inject` is also directly callable — pass a
hand-built scope as `provider=` and the ambient scope is not consulted. See
[Testing with replacement dependencies](../guides/testing.md).

## Checkpoint

```bash
pytest tests/test_shortlinks.py -q
# 3 passed
```

## Where to go from here

- [Concepts](../concepts/index.md) — the model in full.
- [Guides](../guides/index.md) — task-oriented recipes (async, typed config,
  organizing a large container).
- [Architecture](../architecture/index.md) — the same layering as a reference,
  with a different app.
- [API reference](../api/index.md).
