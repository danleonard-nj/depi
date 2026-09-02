# Registration

Registration is the act of telling the container about a type: how to construct
it, and how long an instance should live. All of it happens on a
[`ServiceCollection`][depi.ServiceCollection] before you call
[`build_provider()`][depi.ServiceCollection.build_provider].

Registration is ordinary Python. There is no configuration file and no
decorator; branching, loops, and helper functions all work because it is just
code that runs.

## The `add_*` methods

| Method | Lifetime | Notes |
| --- | --- | --- |
| [`add_singleton`][depi.ServiceCollection.add_singleton] | singleton | accepts `eager=True` to construct at build time |
| [`add_transient`][depi.ServiceCollection.add_transient] | transient | |
| [`add_scoped`][depi.ServiceCollection.add_scoped] | scoped | |
| [`add`][depi.ServiceCollection.add] | transient (default) | shorthand; pass `lifetime=` to change it |
| [`register_many`][depi.ServiceCollection.register_many] | your choice | bulk-register a list of types under one lifetime |

Lifetimes themselves are covered in [Lifetimes and scopes](lifetimes-and-scopes.md).

## Registration forms

Each `add_*` method takes the same set of optional arguments. They are mutually
exclusive ways of answering "how is this made".

### By concrete type

```python
services.add_singleton(Database)
```

`depi` inspects `Database.__init__`, reads the annotation on every parameter,
and resolves each one when it constructs `Database`.

### Interface to implementation

```python
services.add_singleton(EmailSender, SmtpEmailSender)
```

Anything that depends on `EmailSender` gets an `SmtpEmailSender`. The
implementation's constructor is inspected, not the interface's. "Interface" here
is just a type used as a key — an ABC, a `Protocol`, or a plain base class all
work; `depi` does not check that the implementation is a subclass.

### A pre-built instance

```python
services.add_singleton(Config, instance=already_built_config)
```

`resolve(Config)` returns that exact object. Only meaningful for singletons.

### A factory

```python
services.add_singleton(HttpClient, factory=make_http_client)
```

The factory is a callable that receives the provider (or scope) and returns the
instance. Use it when the constructor is not annotated, when construction needs
runtime branching, or when the object comes from a third-party library. See
[Factories](factories.md).

### Registering one object under several types

```python
notifier = Notifier(config)
services.add_singleton(EmailChannel, instance=notifier)
services.add_singleton(SmsChannel, instance=notifier)
```

Registering the same *factory* under several keys produces a separate instance
per key. To share one object, build it and register it as an instance, as above.

## Overriding a registration

Registering the same key twice keeps the last one:

```python
services.add_singleton(Clock, SystemClock)
services.add_singleton(Clock, FrozenClock)   # this wins
```

This is what makes [test containers](../guides/testing.md) straightforward: build
the real registration set, then override the few edges you want to fake.

## Every parameter needs an annotation

```python
class Report:
    def __init__(self, db):        # no annotation
        ...

services.add_transient(Report)
# depi.MissingAnnotationError: Missing type annotation for parameter 'db' in Report
```

The check runs *at the `add_*` call*, because that is when `depi` inspects the
signature. A factory registration skips the check — the factory constructs the
object itself, so `depi` never reads its constructor.

String annotations (`from __future__ import annotations`, or quoted forward
references) are evaluated, so a class whose `__init__` annotations are strings
registers and resolves normally.

## The composition root

The **composition root** is the one place where registration happens and the one
place that knows about concrete implementations. Everything else in the
application depends on interfaces and takes them as constructor parameters.

```python
# composition.py — imported by main(), by nothing else
from depi import ServiceCollection, ServiceProvider

def build_container() -> ServiceProvider:
    services = ServiceCollection()
    services.add_singleton(Config)
    services.add_singleton(Clock, SystemClock)
    services.add_singleton(EmailSender, SmtpEmailSender)
    services.add_scoped(UnitOfWork)
    services.add_transient(RegisterUser)
    return services.build_provider()
```

```python
# main.py
from composition import build_container

def main() -> None:
    provider = build_container()
    provider.resolve(App).run()
```

Keeping this in its own module, imported only by the entry point (and by the
test suite, which has its own variant), is what stops `depi` from spreading into
the codebase. The [Architecture](../architecture/index.md) chapter builds this
out fully. For a container with dozens of registrations, see
[Organizing a large container](../guides/organizing-registrations.md).

## API

- [`ServiceCollection`](../api/container.md#servicecollection)
