# Organizing a large container

**Goal:** keep the composition root readable when it has dozens of
registrations.

Registration is ordinary Python, so the tool is ordinary Python: split it into
functions by role and compose them.

## Group by role

```python
def register_config(services: ServiceCollection) -> None:
    services.add_singleton(RawConfig, instance=load_raw_config())
    register_config_section(services, EmailConfig, "email")
    register_config_section(services, StorageConfig, "storage")

def register_clients(services: ServiceCollection) -> None:
    services.add_singleton(AsyncClient, factory=make_http_client)
    services.add_singleton(AsyncIOMotorClient, factory=make_mongo_client)

def register_repositories(services: ServiceCollection) -> None:
    services.add_scoped(UserRepository, MongoUserRepository)
    services.add_scoped(OrderRepository, MongoOrderRepository)

def register_services(services: ServiceCollection) -> None:
    services.add_transient(RegisterUser)
    services.add_transient(PlaceOrder)
```

```python
def build_container() -> ServiceProvider:
    services = ServiceCollection()
    register_config(services)
    register_clients(services)
    register_repositories(services)
    register_services(services)
    return services.build_provider()
```

Each function is independently readable and independently testable. A test
container can call `register_services(services)` and supply its own fakes for
the rest — see [Testing](testing.md).

## `register_many` for a uniform batch

When a list of types all share a lifetime and have no special construction:

```python
from depi import Lifetime

services.register_many(
    [PriceCalculator, TaxCalculator, DiscountCalculator],
    lifetime=Lifetime.Transient,
)
```

`register_many` does not accept factories or interface mappings; it is for the
plain case.

## Order does not matter (mostly)

Registrations can be added in any order — `build_provider()` works out
construction order from the graph. The one ordering rule: a later registration
for the same key overrides an earlier one, which is deliberate and is what
[test overrides](testing.md) rely on.

## Keep it in one module

All of this stays in `composition.py` (or a `composition/` package with one
module per `register_*` group). It is imported by the entry point and the test
suite, and by nothing else. That boundary is what keeps `depi` out of the rest
of the codebase — see [Architecture](../architecture/index.md).

## What "scales" means here

The API does not change between three registrations and a few hundred. Build
cost is a sub-millisecond, once-at-startup validation pass; resolve cost tracks
the depth of what you asked for, not the container's size. A large container is
a long composition root, not a slow one.
