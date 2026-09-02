# Getting started

This page goes from nothing to a working container. It assumes you know Python
but not `depi`.

## Install

```bash
pip install pydepi
```

That pulls in nothing else. If you are wiring a web application, install the
adapter for your framework as well — `pip install pydepi-flask` (or `-quart`,
`-fastapi`, `-django`). Those are covered in [Integrations](integrations/index.md);
the rest of this page is plain Python.

## The smallest useful example

Three classes, where each depends on the one before it:

```python
from depi import ServiceCollection

class Config:
    def __init__(self):
        self.greeting = "hello"

class Formatter:
    def __init__(self, config: Config):
        self.greeting = config.greeting

    def format(self, name: str) -> str:
        return f"{self.greeting}, {name}"

class Greeter:
    def __init__(self, formatter: Formatter):
        self.formatter = formatter

    def greet(self, name: str) -> str:
        return self.formatter.format(name)
```

`Formatter` needs a `Config`; `Greeter` needs a `Formatter`. The type
annotations on the constructor parameters are what `depi` reads — there are no
decorators or base classes involved.

## Register the dependencies

```python
services = ServiceCollection()
services.add_singleton(Config)
services.add_singleton(Formatter)
services.add_transient(Greeter)
```

[`ServiceCollection`][depi.ServiceCollection] is a list of registrations. Each
`add_*` call says "when something needs this type, here is how to make it, and
here is how long the instance should live":

- [`add_singleton`][depi.ServiceCollection.add_singleton] — one instance for the
  life of the provider.
- [`add_transient`][depi.ServiceCollection.add_transient] — a fresh instance
  every time it is resolved.
- [`add_scoped`][depi.ServiceCollection.add_scoped] — one instance per scope
  (see [below](#scoped-lifetime)).

Every constructor parameter must have a type annotation. An unannotated
parameter raises [`MissingAnnotationError`][depi.MissingAnnotationError] *at the
`add_*` call*, not later:

```python
class Broken:
    def __init__(self, config):        # no annotation
        ...

services.add_singleton(Broken)
# depi.MissingAnnotationError: Missing type annotation for parameter 'config' in Broken
```

## Build the provider and resolve

```python
provider = services.build_provider()

greeter = provider.resolve(Greeter)
print(greeter.greet("world"))          # hello, world
```

[`build_provider()`][depi.ServiceCollection.build_provider] freezes the
registrations into a [`ServiceProvider`][depi.ServiceProvider]. It also
validates the whole graph once, at this point:

- every constructor dependency is registered,
- there are no cycles,
- no singleton depends on a shorter-lived service.

A problem here raises a [`RegistrationError`][depi.RegistrationError] subclass,
so wiring mistakes fail at startup rather than on a request.

[`resolve(Greeter)`][depi.ServiceProvider.resolve] constructs `Greeter`, which
needs a `Formatter`, which needs a `Config`. `depi` builds them in that order
and injects each one.

## Lifetimes, concretely

```python
provider = services.build_provider()

a = provider.resolve(Greeter)
b = provider.resolve(Greeter)
assert a is not b                       # transient: different objects
assert a.formatter is b.formatter       # singleton: shared Formatter
```

`Greeter` is transient, so each `resolve` call returns a new one. `Formatter`
and `Config` are singletons, so the two greeters share the same instances.

### Scoped lifetime

A **scope** is a bounded region — typically one HTTP request — within which
scoped services behave like singletons, and after which they are disposed.

```python
from depi import ServiceCollection

class RequestId:
    _next = 0
    def __init__(self):
        RequestId._next += 1
        self.value = RequestId._next

services = ServiceCollection()
services.add_scoped(RequestId)
provider = services.build_provider()

with provider.create_scope() as scope:
    first = scope.resolve(RequestId)
    second = scope.resolve(RequestId)
    assert first is second              # same instance within the scope

with provider.create_scope() as scope:
    assert scope.resolve(RequestId) is not first   # a different scope, a new instance
```

Resolving a scoped service straight from the provider — with no scope — raises
[`ScopeRequiredError`][depi.ScopeRequiredError]. Scopes are context managers;
when the `with` block exits, any scoped instance that defines a `dispose()`
method has it called. [`async with`](concepts/async.md) is also supported and
awaits async cleanup.

## What you now know

- `ServiceCollection` collects registrations; `build_provider()` validates and
  freezes them.
- `add_singleton` / `add_transient` / `add_scoped` choose the lifetime.
- Dependencies are read from constructor annotations — no unannotated
  parameters.
- `provider.resolve(T)` builds `T` and everything it needs.
- Scoped services need a scope; the scope disposes them on exit.

Next: the [Tutorial](tutorial/index.md) builds a small app with this, step by
step. Or go to [Concepts](concepts/index.md) for the model in full, or
[Architecture](architecture/index.md) for how to structure an application around
this without the container leaking into it.
