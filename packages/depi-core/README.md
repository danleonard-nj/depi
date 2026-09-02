# pydepi

A .NET-inspired, type-hint driven dependency injection container for Python.

`pydepi` resolves dependency graphs from constructor type annotations. It has **no dependencies** and knows nothing about the web — framework support ships as separate packages, so installing the container never drags a web framework into your environment.

```bash
pip install pydepi
```

```python
from depi import ServiceCollection

class Config:
    def __init__(self):
        self.dsn = 'postgres://localhost/app'

class Database:
    def __init__(self, config: Config):      # resolved from the annotation
        self.dsn = config.dsn

services = ServiceCollection()
services.add_singleton(Config)
services.add_scoped(Database)

provider = services.build_provider()

with provider.create_scope() as scope:
    db = scope.resolve(Database)
```

## Lifetimes

- **Transient** – a new instance on every resolution
- **Singleton** – one instance for the life of the provider
- **Scoped** – one instance per scope, typically per HTTP request

Scopes dispose their instances on exit, and `async with` awaits async cleanup first.

## Framework integrations

Each is a separate distribution depending on this one:

| Package          | Import         |
| ---------------- | -------------- |
| `pydepi-flask`   | `depi_flask`   |
| `pydepi-quart`   | `depi_quart`   |
| `pydepi-fastapi` | `depi_fastapi` |
| `pydepi-django`  | `depi_django`  |

Install one by name — `pip install pydepi-flask`. The extra `pydepi[flask]` works too, but the
distribution name is the more accurate form: these are separate packages, versioned and released
independently of core, not optional features of it.

Full documentation, including the integration guide, factories, and the async API, is in the [project README](https://github.com/danleonard-nj/depi#readme).

## License

MIT
