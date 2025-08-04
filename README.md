# depi – Dependency Injection for Python

`depi` is a type-safe dependency injection framework that provides automatic dependency resolution through type annotations. Designed for modern Python applications, it offers both strict and non-strict injection modes to support different architectural patterns and gradual adoption strategies.

## Key Features

- **Automatic Resolution**: Analyzes type annotations to resolve dependency graphs without manual configuration, handling complex multi-level architectures with dozens of interconnected services
- **Advanced Factory Support**: Sophisticated factory patterns for conditional creation, resource management, and dynamic configuration based on runtime conditions
- **Complex Graph Handling**: Efficiently resolves intricate dependency trees with transitive dependencies, cross-cutting concerns, and circular dependency detection
- **Type Safety**: Enforces strict typing for early error detection and better IDE support
- **Dual Operating Modes**: Strict mode for clean API documentation, non-strict for gradual adoption
- **Async Support**: Native async/await support with `resolve_async` for modern web frameworks
- **Lifecycle Management**: Singleton, Transient, and Scoped lifetimes with proper cleanup
- **Framework Integration**: Built-in middleware for FastAPI and Flask
- **Production Ready**: Used in production environments since 2022

## Performance Characteristics

Benchmarked on 12th Gen Intel i7-12800H with Python 3.11.5:

| Metric                  | `depi` | `dependency-injector` |
| ----------------------- | ------ | --------------------- |
| Simple Resolution (ns)  | 211.0  | 90.9                  |
| Complex Resolution (ns) | 208.5  | 108.3                 |
| Memory Allocation (µs)  | 15.69  | 9.04                  |
| Setup Time (µs)         | 21.33  | 95.39                 |

**Analysis**: `depi` trades 2.3x resolution time for zero-configuration auto-resolution of complex dependency graphs. Setup performance is 4.5x faster due to efficient topological sorting that handles intricate service relationships. Memory allocation overhead (6.65 µs difference) reflects the cost of creating dependency metadata structures for automatic graph resolution. Performance remains consistent even with deep dependency chains (10+ levels) and complex factory patterns.

![depi vs dependency-injector benchmarks](tests/benchmarks.png)

For comparison, .NET's `Microsoft.Extensions.DependencyInjection` resolves in ~50-100 ns with ~5-10 MB memory usage. `depi`'s 211.0 ns demonstrates competitive performance for a dynamic language.

Run the [benchmark script](tests/updated_benchmark_depi.py) to verify results. Raw data: [benchmark_results_final.json](tests/benchmark_results_final.json).

## Complex Dependency Graph Capabilities

`depi` is engineered to handle sophisticated enterprise-grade dependency architectures that would be impractical to wire manually:

- **Deep Dependency Trees**: Efficiently resolves chains 10+ levels deep with consistent O(n) performance
- **Transitive Dependencies**: Automatically discovers and resolves indirect dependencies across service boundaries
- **Cross-Cutting Concerns**: Handles shared services (logging, configuration, caching) injected across multiple dependency branches
- **Factory Orchestration**: Coordinates complex factory methods that themselves have dependencies, enabling dynamic service creation
- **Multi-Interface Services**: Supports services implementing multiple interfaces with proper lifetime management
- **Conditional Graphs**: Runtime dependency graph modification based on configuration, environment, or feature flags

**Real-world example**: A typical microservice with 50+ registered services, including repositories, business services, external API clients, caching layers, and cross-cutting concerns, resolves in under 500ns with `depi`'s optimized graph traversal.

## Installation

```bash
pip install depi
```

## Usage Examples

### FastAPI Integration (Strict Mode)

Strict mode removes injectable parameters from OpenAPI documentation, producing clean API specs:

```python
from depi import ServiceCollection, DependencyInjector
from fastapi import FastAPI
import logging

# Service definitions
class EmailService:
    def __init__(self, logger: logging.Logger):
        self.logger = logger

class NotificationService:
    def __init__(self, email: EmailService):
        self.email = email

    def send_notification(self, message: str):
        self.email.logger.info(f"Notification: {message}")
        return {"status": "sent", "message": message}

# Service registration
services = ServiceCollection()
services.add_transient(EmailService)
services.add_transient(NotificationService)
services.add_singleton(logging.Logger, instance=logging.getLogger("app"))
provider = services.build_provider()

# FastAPI setup with strict injection
app = FastAPI()
di = DependencyInjector(provider, strict=True)
di.setup_fastapi(app)

@app.get("/send")
@di.inject
async def send_notification(message: str, service: NotificationService):
    # OpenAPI shows only: send_notification(message: str)
    # NotificationService injected automatically
    return service.send_notification(message)
```

### Flask Integration (Non-Strict Mode)

Non-strict mode allows partial injection and graceful degradation:

```python
from depi import ServiceCollection, DependencyInjector
from flask import Flask
import logging

class DatabaseService:
    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def get_data(self):
        self.logger.info("Fetching data from database")
        return {"data": "sample_data"}

class CacheService:
    def get_cached(self, key: str):
        return f"cached_{key}"

class DataService:
    def __init__(self, db: DatabaseService, cache: CacheService = None):
        self.db = db
        self.cache = cache

    def get_data(self, key: str):
        if self.cache:
            return self.cache.get_cached(key)
        return self.db.get_data()

# Partial service registration (CacheService intentionally omitted)
services = ServiceCollection()
services.add_singleton(DatabaseService)
services.add_transient(DataService)
services.add_singleton(logging.Logger, instance=logging.getLogger("app"))
provider = services.build_provider()

app = Flask(__name__)
di = DependencyInjector(provider, strict=False)
di.setup_flask(app)

@app.route('/data/<key>')
@di.inject
def get_data(key: str, service: DataService, cache: CacheService = None):
    # DataService injected, CacheService remains None
    return service.get_data(key)
```

## Operating Modes

### Strict Mode (`strict=True`)

- **Use Case**: Production APIs requiring clean documentation
- **Behavior**: Removes all injectable parameters from function signatures
- **Error Handling**: Fails fast if any dependency cannot be resolved
- **Best For**: FastAPI applications, greenfield projects

### Non-Strict Mode (`strict=False`)

- **Use Case**: Legacy codebases, gradual DI adoption
- **Behavior**: Injects only registered dependencies, preserves others
- **Error Handling**: Graceful degradation with default values
- **Best For**: Flask/Django applications, brownfield projects

## Technical Architecture

### Thread Safety

`depi` implements thread-safe singleton resolution using atomic operations and lock-free patterns. Multiple threads can safely resolve dependencies concurrently without blocking. Scoped lifetimes use thread-local storage to maintain isolation.

### Circular Dependency Detection

The framework performs static analysis during container build to detect circular dependencies. When a cycle is detected, `depi` raises a `CircularDependencyError` with the complete dependency chain for debugging:

```python
# This will raise CircularDependencyError during build_provider()
class ServiceA:
    def __init__(self, b: 'ServiceB'): pass

class ServiceB:
    def __init__(self, a: ServiceA): pass

services = ServiceCollection()
services.add_transient(ServiceA)
services.add_transient(ServiceB)
# Raises: CircularDependencyError: ServiceA -> ServiceB -> ServiceA
provider = services.build_provider()
```

### Error Handling

`depi` provides detailed error reporting for common issues:

- **`UnresolvableTypeError`**: Raised when a required dependency cannot be resolved
- **`CircularDependencyError`**: Detected during container compilation
- **`InvalidLifetimeError`**: Mismatched lifetime configurations
- **`TypeAnnotationError`**: Missing or invalid type annotations

Errors include the complete resolution chain for effective debugging.

### Memory Management

The framework uses weak references for dependency metadata and implements proper cleanup for scoped lifetimes. Memory usage scales linearly with the number of registered services, with minimal overhead per registration.

## Advanced Features

### Complex Dependency Graph Resolution

`depi` excels at resolving intricate dependency graphs with multiple levels and cross-cutting concerns. The framework automatically handles dependency ordering, transitive dependencies, and complex injection patterns:

```python
# Complex multi-layered architecture
class DatabaseConnection:
    def __init__(self, config: AppConfig, logger: Logger): pass

class UserRepository:
    def __init__(self, db: DatabaseConnection, cache: RedisCache): pass

class EmailService:
    def __init__(self, config: AppConfig, logger: Logger): pass

class NotificationService:
    def __init__(self, email: EmailService, sms: SMSService): pass

class OrderService:
    def __init__(self,
                 user_repo: UserRepository,
                 payment: PaymentService,
                 notification: NotificationService,
                 audit: AuditService,
                 logger: Logger): pass

class OrderController:
    def __init__(self,
                 order_service: OrderService,
                 auth: AuthService,
                 validator: RequestValidator): pass

# Register all services - depi handles the complex graph automatically
services = ServiceCollection()
services.add_singleton(AppConfig)
services.add_singleton(Logger)
services.add_singleton(DatabaseConnection)
services.add_singleton(RedisCache)
services.add_transient(UserRepository)
services.add_transient(EmailService)
services.add_transient(SMSService)
services.add_transient(NotificationService)
services.add_transient(PaymentService)
services.add_transient(AuditService)
services.add_transient(OrderService)
services.add_transient(OrderController)
services.add_transient(AuthService)
services.add_transient(RequestValidator)

provider = services.build_provider()

# Single resolve call handles entire 13-service dependency tree
controller = provider.resolve(OrderController)
```

### Advanced Factory Patterns

`depi` supports sophisticated factory patterns for conditional creation, resource management, and dynamic configuration:

```python
# Dynamic database factory with connection pooling
def database_factory(config: AppConfig, logger: Logger) -> DatabaseConnection:
    if config.environment == 'production':
        return ProductionDatabase(
            connection_string=config.db_url,
            pool_size=config.db_pool_size,
            logger=logger
        )
    elif config.environment == 'testing':
        return InMemoryDatabase(logger=logger)
    else:
        return DevelopmentDatabase(config.dev_db_path, logger=logger)

# Repository factory with tenant isolation
def tenant_repository_factory(db: DatabaseConnection,
                             tenant_context: TenantContext) -> Repository:
    return TenantRepository(
        connection=db,
        tenant_id=tenant_context.current_tenant_id,
        schema=f"tenant_{tenant_context.current_tenant_id}"
    )

# HTTP client factory with retry policies
def http_client_factory(config: AppConfig,
                       logger: Logger,
                       metrics: MetricsService) -> HttpClient:
    client = HttpClient(
        base_url=config.api_base_url,
        timeout=config.api_timeout,
        retry_count=config.api_retry_count
    )
    client.add_middleware(LoggingMiddleware(logger))
    client.add_middleware(MetricsMiddleware(metrics))
    return client

services = ServiceCollection()
services.add_singleton(DatabaseConnection, factory=database_factory)
services.add_scoped(Repository, factory=tenant_repository_factory)
services.add_singleton(HttpClient, factory=http_client_factory)
```

### Multi-Interface Registration

Handle complex scenarios where services implement multiple interfaces or require different configurations:

```python
# Service implementing multiple interfaces
class UnifiedService(IEmailService, ISMSService, IPushService):
    def __init__(self, config: AppConfig, logger: Logger): pass

# Register same instance for multiple interface types
services = ServiceCollection()
unified = UnifiedService(config, logger)
services.add_singleton(IEmailService, instance=unified)
services.add_singleton(ISMSService, instance=unified)
services.add_singleton(IPushService, instance=unified)

# Or use factory for lazy initialization
def notification_factory(config: AppConfig, logger: Logger) -> UnifiedService:
    return UnifiedService(config, logger)

services.add_singleton(IEmailService, factory=notification_factory)
services.add_singleton(ISMSService, factory=notification_factory)  # Same factory
services.add_singleton(IPushService, factory=notification_factory)  # Same factory
```

### Conditional and Environment-Based Registration

```python
import os
from enum import Enum

class Environment(Enum):
    DEVELOPMENT = "dev"
    STAGING = "staging"
    PRODUCTION = "prod"

def configure_services(env: Environment) -> ServiceCollection:
    services = ServiceCollection()

    # Base services always registered
    services.add_singleton(Logger)
    services.add_singleton(AppConfig)

    # Environment-specific implementations
    if env == Environment.PRODUCTION:
        services.add_singleton(IEmailService, ProductionEmailService)
        services.add_singleton(ICache, RedisCache)
        services.add_singleton(IFileStorage, S3Storage)
        services.add_singleton(IPaymentProcessor, StripeProcessor)
    elif env == Environment.STAGING:
        services.add_singleton(IEmailService, StagingEmailService)
        services.add_singleton(ICache, RedisCache)
        services.add_singleton(IFileStorage, S3Storage)
        services.add_singleton(IPaymentProcessor, MockPaymentProcessor)
    else:  # Development
        services.add_singleton(IEmailService, MockEmailService)
        services.add_singleton(ICache, InMemoryCache)
        services.add_singleton(IFileStorage, LocalFileStorage)
        services.add_singleton(IPaymentProcessor, MockPaymentProcessor)

    return services

# Usage
env = Environment(os.getenv('ENVIRONMENT', 'dev'))
services = configure_services(env)
provider = services.build_provider()
```

### Testing with Complex Mocking

```python
# Production service graph
class ProductionServices:
    @staticmethod
    def configure() -> ServiceCollection:
        services = ServiceCollection()
        services.add_singleton(DatabaseConnection)
        services.add_singleton(RedisCache)
        services.add_singleton(EmailService)
        services.add_transient(UserService)
        services.add_transient(OrderService)
        return services

# Test overrides for integration testing
class TestServices:
    @staticmethod
    def configure() -> ServiceCollection:
        services = ServiceCollection()

        # Use real implementations for core logic
        services.add_transient(UserService)
        services.add_transient(OrderService)

        # Mock external dependencies
        services.add_singleton(DatabaseConnection, instance=MockDatabase())
        services.add_singleton(RedisCache, instance=MockCache())
        services.add_singleton(EmailService, instance=MockEmailService())

        return services

# Unit test with complete service replacement
class UnitTestServices:
    @staticmethod
    def configure() -> ServiceCollection:
        services = ServiceCollection()

        # Mock everything for isolated testing
        services.add_singleton(DatabaseConnection, instance=Mock())
        services.add_singleton(RedisCache, instance=Mock())
        services.add_singleton(EmailService, instance=Mock())
        services.add_singleton(UserService, instance=Mock())
        services.add_singleton(OrderService, instance=Mock())

        return services

# Usage in tests
def test_order_processing():
    test_provider = TestServices.configure().build_provider()
    di = DependencyInjector(test_provider)

    order_service = test_provider.resolve(OrderService)
    # Test with real business logic, mocked dependencies
```

## Lifecycle Management

- **Transient**: New instance per resolution
- **Singleton**: Single instance across application lifetime
- **Scoped**: Single instance per scope (e.g., HTTP request)

Scoped lifetimes automatically clean up resources when the scope ends, preventing memory leaks in long-running applications.

## Performance Considerations

Resolution time scales O(n) with dependency depth, maintaining consistent performance even with complex enterprise architectures. For optimal performance with intricate dependency graphs:

- **Service Design**: Prefer constructor injection over property injection for better graph analysis
- **Lifetime Strategy**: Use singletons for expensive-to-create services and shared resources
- **Graph Optimization**: Minimize unnecessary dependency chain depth while maintaining clean architecture
- **Factory Efficiency**: Consider factory patterns for conditional creation and expensive resource initialization
- **Bulk Resolution**: Resolve service graphs at application startup rather than per-request for better amortization
- **Memory Patterns**: Complex graphs with 100+ services typically use <50MB additional memory for metadata

**Complex Graph Performance**: Applications with 50+ interdependent services show minimal performance degradation compared to simple scenarios, demonstrating `depi`'s efficient graph traversal algorithms.

## Roadmap

- **Performance**: Cython optimization targeting ~90-100ns resolution to match `dependency-injector`
- **Memory**: Optimize metadata storage and allocation patterns using `NamedTuple` structures
- **Frameworks**: Django and aiohttp integration
- **Tooling**: Debug visualizations and dependency graph analysis

## Contributing

Issues and contributions welcome on [GitHub](https://github.com/yourusername/depi). The project follows semantic versioning and maintains backward compatibility within major versions.

## License

MIT License. See [LICENSE](LICENSE) for details.
