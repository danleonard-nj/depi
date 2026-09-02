# Testing with replacement dependencies

**Goal:** run the real application logic against fake infrastructure, without a
"test mode" flag or a conditional import in production code.

The mechanism is [registration override](../concepts/registration.md#overriding-a-registration):
the last registration for a key wins. Build the real set, replace the edges.

## A test container helper

```python
from depi import ServiceCollection

from composition import register_domain          # the real registrations, minus infra
from domain.ports import Clock, EmailSender, UserRepository

def test_container(**overrides):
    services = ServiceCollection()
    register_domain(services)                    # RegisterUser, validators, etc.

    services.add_scoped(UserRepository, InMemoryUserRepository)
    services.add_singleton(EmailSender, instance=CollectingEmailSender())
    services.add_singleton(Clock, instance=FixedClock("2020-01-01T00:00:00+00:00"))

    for key, impl in overrides.items():
        services.add_singleton(key, instance=impl)

    return services.build_provider()
```

Split your composition root so the parts you always want (application services,
domain policies) are separated from infrastructure. See
[Organizing a large container](organizing-registrations.md). The test helper
reuses the first and supplies its own second.

## Using it

```python
def test_registers_a_user():
    provider = test_container()
    with provider.create_scope() as scope:
        register = scope.resolve(RegisterUser)
        user = register("a@example.com")
    assert user.email == "a@example.com"
```

Scoped services need a scope even in a test — `with provider.create_scope()`.
The scope also disposes anything it created, so a fake holding a transaction gets
its `dispose()` called.

## Overriding one dependency in one test

```python
def test_surfaces_a_repository_failure():
    class FailingRepo:
        def by_email(self, email): raise ConnectionError("db down")
        def add(self, user): ...

    provider = test_container(**{UserRepository.__name__: None})  # or:
    services = ServiceCollection()
    register_domain(services)
    services.add_scoped(UserRepository, FailingRepo)
    provider = services.build_provider()

    with provider.create_scope() as scope:
        with pytest.raises(ConnectionError):
            scope.resolve(RegisterUser)("a@example.com")
```

## Mock objects as instances

An `unittest.mock.Mock` can be registered as an instance:

```python
from unittest.mock import Mock

repo = Mock(spec=UserRepository)
repo.by_email.return_value = None

services.add_scoped(UserRepository, instance=repo)
```

Register it as an instance, not a factory, so the same mock object is the one
your assertions inspect.

## Calling a decorated view directly

A view wrapped with `@injector.inject` can be called without a request by
passing the scope yourself — the ambient scope is only consulted for arguments
you did not supply:

```python
with provider.create_scope() as scope:
    response, status = register(provider=scope)
```

## Skipping the container entirely

If a class only takes constructor parameters, a unit test does not need `depi`
at all:

```python
def test_register_user_logic():
    register = RegisterUser(InMemoryUserRepository(), FixedClock("2020-01-01T00:00:00+00:00"))
    assert register("a@example.com").email == "a@example.com"
```

Reserve the container for tests that exercise the wiring — that scoped disposal
happens, that an autowired view resolves, that `build_provider()` accepts the
real registration set.
