# Third-party clients and factories

**Goal:** register objects from libraries whose constructors `depi` cannot read.

`depi` builds a type by resolving each annotated `__init__` parameter. An SDK
client typically has a constructor like `Client(api_key, *, timeout=None,
base_url=None, ...)` — positional, unannotated, or expecting plain values. There
is nothing for `depi` to resolve. Wrap it in a [factory](../concepts/factories.md).

## The pattern

```python
from motor.motor_asyncio import AsyncIOMotorClient

def make_mongo_client(provider) -> AsyncIOMotorClient:
    config = provider.resolve(AppConfig)
    return AsyncIOMotorClient(config.mongo_connection_string)

services.add_singleton(AsyncIOMotorClient, factory=make_mongo_client)
```

The factory receives the provider, so it can resolve whatever the client needs
— a connection string, credentials, a shared logger. Downstream code takes
`AsyncIOMotorClient` as a constructor parameter and gets the configured
instance.

## Clients with no dependencies

Still use a factory — it is the place the construction arguments live:

```python
from httpx import AsyncClient, Limits

def make_http_client(provider) -> AsyncClient:
    return AsyncClient(timeout=30.0, limits=Limits(max_connections=100))

services.add_singleton(AsyncClient, factory=make_http_client)
```

## Async clients that connect

```python
async def make_kafka_producer(provider) -> AIOKafkaProducer:
    producer = AIOKafkaProducer(bootstrap_servers=provider.resolve(AppConfig).kafka_brokers)
    await producer.start()
    return producer

services.add_singleton(AIOKafkaProducer, factory=make_kafka_producer)
```

A singleton async factory runs during `build_provider()`. See
[Async dependencies](async-dependencies.md).

## Several implementations behind one interface

When callers want a *specific* provider (not "any LLM client"), register each by
its concrete type. Each gets its own SDK client, config, and cache injected via
its own constructor:

```python
services.add_singleton(OpenAIChatProvider)
services.add_singleton(AnthropicChatProvider)
services.add_singleton(GoogleChatProvider)
```

A dispatcher that needs all three takes them as three constructor parameters.

## Sharing one client under multiple keys

A factory registered under two keys produces two clients. To share one:

```python
client = build_unified_client(config)
services.add_singleton(ReadClient, instance=client)
services.add_singleton(WriteClient, instance=client)
```

## Where factories belong

Next to the registrations, in the [composition root](../concepts/registration.md#the-composition-root)
— often as module-level functions in the same file, or grouped into a
`register_clients(services)` function (see
[Organizing a large container](organizing-registrations.md)). Application code
never imports the factory; it only names the client type in a constructor.
