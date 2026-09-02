# 3. Wiring it together

Now the concrete implementations, the composition root, and a script that runs
the whole thing.

## Infrastructure

> File: `shortlinks/infrastructure.py`

```python
# shortlinks/infrastructure.py
import logging
import os
import secrets
import string
from datetime import datetime, timezone

from shortlinks.domain import Link

log = logging.getLogger("shortlinks")
_ALPHABET = string.ascii_lowercase + string.digits


class AppConfig:
    def __init__(self, code_length: int):
        self.code_length = code_length


class LinkStore:
    """Stands in for a database. One instance holds every link."""

    def __init__(self):
        self._rows: dict[str, Link] = {}

    def put(self, link: Link) -> None:
        self._rows[link.code] = link

    def get(self, code: str) -> Link | None:
        return self._rows.get(code)

    def bump(self, code: str) -> None:
        if code in self._rows:
            self._rows[code].hits += 1


class SqlLikeLinkRepository:
    """
    One per request, like a database session. New links are buffered and
    written to the store when the request's scope is disposed.
    """

    def __init__(self, store: LinkStore):
        self._store = store
        self._pending: list[Link] = []

    def add(self, link: Link) -> None:
        self._pending.append(link)

    def by_code(self, code: str) -> Link | None:
        for link in self._pending:
            if link.code == code:
                return link
        return self._store.get(code)

    def record_hit(self, code: str) -> None:
        self._store.bump(code)

    def dispose(self) -> None:
        for link in self._pending:
            self._store.put(link)
        if self._pending:
            log.info("flushed %d link(s)", len(self._pending))
        self._pending.clear()


class RandomCodeGenerator:
    def __init__(self, config: AppConfig):
        self._length = config.code_length

    def next(self) -> str:
        return "".join(secrets.choice(_ALPHABET) for _ in range(self._length))


class SystemClock:
    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()


def load_config(_provider) -> AppConfig:
    return AppConfig(code_length=int(os.environ.get("SHORTLINK_CODE_LENGTH", "6")))
```

Still no `depi` import — these are classes that take their own dependencies as
constructor parameters (`SqlLikeLinkRepository` needs a `LinkStore`,
`RandomCodeGenerator` needs an `AppConfig`).

`SqlLikeLinkRepository.dispose()` is the hook `depi` calls when a scope ends. It
flushes buffered writes — the reason this repository is *scoped* rather than a
singleton.

## The composition root

> File: `shortlinks/composition.py`

This is the first and only module that imports `depi`.

```python
# shortlinks/composition.py
from depi import ServiceCollection, ServiceProvider

from shortlinks.domain import Clock, CodeGenerator, LinkRepository
from shortlinks.infrastructure import (
    AppConfig,
    LinkStore,
    RandomCodeGenerator,
    SqlLikeLinkRepository,
    SystemClock,
    load_config,
)
from shortlinks.service import CreateLink, FollowLink


def build_provider() -> ServiceProvider:
    services = ServiceCollection()

    # Singletons: one instance for the process.
    services.add_singleton(AppConfig, factory=load_config)   # (1)!
    services.add_singleton(LinkStore)                         # (2)!
    services.add_singleton(CodeGenerator, RandomCodeGenerator)
    services.add_singleton(Clock, SystemClock)

    # Scoped: one instance per request.
    services.add_scoped(LinkRepository, SqlLikeLinkRepository)  # (3)!

    # Transient: a fresh instance per resolution.
    services.add_transient(CreateLink)                         # (4)!
    services.add_transient(FollowLink)

    return services.build_provider()                           # (5)!
```

1. A [factory](../concepts/factories.md) because the value comes from the
   environment, not from another registered type. It receives the provider (here
   unused) and returns the object.
2. Registered by concrete type — `depi` reads `LinkStore.__init__`, sees no
   parameters, and constructs it directly.
3. `SqlLikeLinkRepository` is registered under the `LinkRepository` interface.
   Anything that depends on `LinkRepository` gets one, and its `dispose()` runs
   at scope end.
4. Application services are cheap and stateless per call — no reason to share
   them, so transient. A transient may depend on a scoped service
   (`CreateLink` needs `LinkRepository`); the reverse is not allowed.
5. `build_provider()` validates the whole graph — every dependency registered,
   no cycles, no singleton depending on something shorter-lived — and returns
   the provider. A wiring mistake fails here.

### Why these lifetimes

| Service | Lifetime | Reason |
| --- | --- | --- |
| `AppConfig`, `LinkStore` | singleton | shared state / config; one for the process |
| `CodeGenerator`, `Clock` | singleton | stateless, safe to share |
| `LinkRepository` | scoped | acts like a DB session — buffered writes, flushed on `dispose()` |
| `CreateLink`, `FollowLink` | transient | one-shot use cases, nothing to share |

See [Lifetimes and scopes](../concepts/lifetimes-and-scopes.md).

## Run it

> File: `shortlinks/cli.py`

```python
# shortlinks/cli.py
import logging

from shortlinks.composition import build_provider
from shortlinks.service import CreateLink, FollowLink

logging.basicConfig(level=logging.INFO)


def main() -> None:
    provider = build_provider()

    # First "request": create a link.
    with provider.create_scope() as scope:
        link = scope.resolve(CreateLink)("https://peps.python.org/pep-0020/")
        print("created:", link.code, "->", link.target)
    # scope disposed here -> SqlLikeLinkRepository.dispose() flushes the new link

    # Second "request": follow it.
    with provider.create_scope() as scope:
        target = scope.resolve(FollowLink)(link.code)
        print("followed:", link.code, "->", target)


if __name__ == "__main__":
    main()
```

```bash
python -m shortlinks.cli
```

```text
INFO:shortlinks:flushed 1 link(s)
created: q7f2ak -> https://peps.python.org/pep-0020/
followed: q7f2ak -> https://peps.python.org/pep-0020/
```

The link created in the first scope survives into the second because
`dispose()` flushed it to the singleton `LinkStore`. Each scope got its own
`SqlLikeLinkRepository`; both share the one `LinkStore`.

Resolving `CreateLink` straight from the provider — `provider.resolve(CreateLink)`
with no scope — would raise [`ScopeRequiredError`][depi.ScopeRequiredError],
because it depends on the scoped `LinkRepository`.

## Checkpoint

`python -m shortlinks.cli` prints a created and followed link, and logs one
flush. Next: the same app behind a web framework.
