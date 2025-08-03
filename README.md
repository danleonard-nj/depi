# depi: Modern Dependency Injection for Python

**depi** is a lightweight, type-safe dependency injection framework designed for modern Python applications. Inspired by .NET's dependency injection patterns, depi brings familiar DI concepts to Python with first-class async support and clean, Pythonic APIs.

Perfect for FastAPI applications, microservices, and any Python project that needs clean dependency management.

---

## Why Choose depi?

- **🎯 Type-Safe**: Full type hint support with mypy and Pyright compatibility
- **⚡ Async Native**: Built-in support for async factories and async context managers
- **🔄 Familiar Patterns**: .NET-inspired API (`add_singleton`, `add_transient`, `add_scoped`)
- **🏗️ Flexible Registration**: Constructor injection, factories, and instance registration
- **🧵 Thread-Safe**: Safe for multi-threaded applications with proper locking
- **📦 Lightweight**: Minimal dependencies, focused on core DI functionality

---

## Installation

```bash
pip install depi
```

**Requires Python 3.8+**

---

## Quick Start

### Basic Usage

```python
from depi import ServiceCollection, Lifetime

# Define your services
class DatabaseConfig:
    def __init__(self):
        self.connection_string = "sqlite:///app.db"

class UserRepository:
    def __init__(self, config: DatabaseConfig):
        self.config = config

    def get_user(self, user_id: int):
        # Database logic here
        return {"id": user_id, "name": "John Doe"}

class UserService:
    def __init__(self, repo: UserRepository):
        self.repo = repo

    def get_user_profile(self, user_id: int):
        return self.repo.get_user(user_id)

# Configure container
container = ServiceCollection()
container.add_singleton(DatabaseConfig)
container.add_singleton(UserRepository)
container.add_transient(UserService)

# Build and use
provider = container.build_provider()
user_service = provider.resolve(UserService)
profile = user_service.get_user_profile(123)
```

### Async Factories

```python
import asyncio
from httpx import AsyncClient

async def create_http_client(provider) -> AsyncClient:
    """Async factory for HTTP client with custom config"""
    config = provider.resolve(ApiConfig)
    client = AsyncClient(
        timeout=config.timeout,
        headers={"User-Agent": "MyApp/1.0"}
    )
    # Perform async setup
    await client.get(f"{config.base_url}/health")
    return client

container = ServiceCollection()
container.add_singleton(ApiConfig)
container.add_singleton(AsyncClient, factory=create_http_client)

provider = await container.build_provider().build_async()
```

### Scoped Dependencies

```python
# Perfect for request-scoped dependencies
container.add_scoped(DatabaseSession)
container.add_scoped(RequestContext)

# Use with context manager
with provider.create_scope() as scope:
    # All scoped dependencies share same instance within this scope
    service1 = scope.resolve(UserService)
    service2 = scope.resolve(OrderService)
    # Same DatabaseSession instance injected into both
```

---

## Framework Integration

### FastAPI Integration

```python
from fastapi import FastAPI, Depends
from depi import ServiceCollection

# Configure your container
container = ServiceCollection()
container.add_singleton(DatabaseConfig)
container.add_scoped(UserRepository)
container.add_scoped(UserService)

provider = container.build_provider()
app = FastAPI()

# Create a dependency function
def get_user_service() -> UserService:
    with provider.create_scope() as scope:
        return scope.resolve(UserService)

@app.get("/users/{user_id}")
async def get_user(user_id: int, service: UserService = Depends(get_user_service)):
    return service.get_user_profile(user_id)
```

### Flask Integration

```python
from flask import Flask, g
from depi import ServiceCollection

container = ServiceCollection()
container.add_singleton(DatabaseConfig)
container.add_scoped(UserRepository)

provider = container.build_provider()
app = Flask(__name__)

@app.before_request
def before_request():
    g.scope = provider.create_scope()

@app.teardown_request
def teardown_request(exception=None):
    if hasattr(g, 'scope'):
        g.scope.dispose()

@app.route('/users/<int:user_id>')
def get_user(user_id):
    service = g.scope.resolve(UserService)
    return service.get_user_profile(user_id)
```

---

## Advanced Features

### Factory Functions

```python
def create_database_session(provider):
    config = provider.resolve(DatabaseConfig)
    engine = create_engine(config.connection_string)
    return sessionmaker(bind=engine)()

container.add_scoped(DatabaseSession, factory=create_database_session)
```

### Conditional Registration

```python
def configure_cache(provider):
    config = provider.resolve(AppConfig)
    if config.environment == "production":
        return RedisCache(config.redis_url)
    else:
        return InMemoryCache()

container.add_singleton(CacheInterface, factory=configure_cache)
```

### Bulk Registration

```python
# Register multiple services with same lifetime
container.register_many([
    UserRepository,
    OrderRepository,
    ProductRepository
], lifetime=Lifetime.Singleton)
```

---

## Comparison with Other DI Frameworks

| Feature                           | depi | dependency-injector | injector | pinject |
| --------------------------------- | :--: | :-----------------: | :------: | :-----: |
| **Type Safety**                   |  ✅  |       Partial       |    ✅    | Partial |
| **Async Factories**               |  ✅  |       Partial       |    ❌    |   ❌    |
| **Async Context Managers**        |  ✅  |         ❌          |    ❌    |   ❌    |
| **True Scoped Lifetimes**         |  ✅  |      Manual\*       |    ✅    |   ❌    |
| **Automatic Scope Cleanup**       |  ✅  |       Manual        |    ✅    |   ❌    |
| **Factory Functions**             |  ✅  |         ✅          |    ✅    |   ❌    |
| **Thread Safety**                 |  ✅  |         ✅          |    ✅    | Partial |
| **Constructor Auto-Detection**    |  ✅  |         ❌          |    ❌    |   ✅    |
| **Cyclic Dependency Detection**   |  ✅  |         ❌          |    ❌    |   ❌    |
| **Lifetime Validation**           |  ✅  |         ❌          |    ❌    |   ❌    |
| **Framework Integration Helpers** |  ✅  |         ❌          | Partial  |   ❌    |
| **Strict Mode**                   |  ✅  |         ❌          |    ❌    |   ❌    |
| **Topological Sorting**           |  ✅  |         ❌          |    ❌    |   ❌    |
| **Performance Caching**           |  ✅  |         ✅          |    ❌    |   ❌    |
| **.NET-Style API**                |  ✅  |         ❌          |    ❌    |   ❌    |

**Key Advantages:**

- **🚀 Async-First**: Native async/await support throughout, including async factories and context managers
- **🔒 Lifecycle Safety**: Prevents transient dependencies in singletons, detects circular dependencies
- **🎯 Developer Experience**: Familiar .NET patterns, automatic dependency detection, clear error messages
- **⚡ Performance**: Constructor caching, topological sorting for optimal resolution order
- **🔧 Framework Ready**: Built-in FastAPI/Flask middleware, no additional configuration needed

\*dependency-injector requires manual scope management using Resource providers or resetting singletons

---

## Error Handling

depi provides clear error messages for common DI issues:

```python
# Circular dependency detection
# DependencyError: Cyclic dependency detected involving 'UserService'

# Missing registration
# DependencyError: Failed to locate registration for type 'DatabaseConfig'

# Lifetime violations
# DependencyError: Cannot inject transient 'Logger' into singleton 'UserService'
```

---

## Best Practices

### 1. Use Interface-Based Design

```python
from abc import ABC, abstractmethod

class IUserRepository(ABC):
    @abstractmethod
    def get_user(self, user_id: int): pass

class SqlUserRepository(IUserRepository):
    def get_user(self, user_id: int):
        # SQL implementation
        pass

# Register interface to implementation
container.add_singleton(IUserRepository, SqlUserRepository)
```

### 2. Configure Once, Use Everywhere

```python
def configure_services() -> ServiceCollection:
    container = ServiceCollection()

    # Infrastructure
    container.add_singleton(DatabaseConfig)
    container.add_singleton(ILogger, ConsoleLogger)

    # Repositories
    container.add_singleton(IUserRepository, SqlUserRepository)

    # Services
    container.add_transient(UserService)

    return container

# Use in your application
container = configure_services()
provider = container.build_provider()
```

### 3. Leverage Scopes for Request Handling

```python
# In web applications, create a scope per request
async def handle_request(request):
    async with provider.create_scope() as scope:
        handler = await scope.resolve_async(RequestHandler)
        return await handler.process(request)
```

---

## API Reference

### ServiceCollection

- `add_singleton(type, implementation=None, instance=None, factory=None)`
- `add_transient(type, implementation=None, factory=None)`
- `add_scoped(type, implementation=None, factory=None)`
- `register_many(types, lifetime=Lifetime.Transient)`

### ServiceProvider

- `resolve(type) -> instance`
- `resolve_async(type) -> Awaitable[instance]`
- `create_scope() -> ServiceScope`

### ServiceScope

- `resolve(type) -> instance`
- `resolve_async(type) -> Awaitable[instance]`
- `dispose()`

---

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

- **Issues**: Bug reports and feature requests
- **Pull Requests**: Fork, implement, test, and submit PRs
- **Documentation**: Help improve our docs and examples

---

## License

MIT License - see [LICENSE](LICENSE) file for details.

---

## Support

- 📖 **Documentation**: [Read the full docs](https://depi.readthedocs.io)
- 🐛 **Issues**: [GitHub Issues](https://github.com/yourusername/depi/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/yourusername/depi/discussions)
