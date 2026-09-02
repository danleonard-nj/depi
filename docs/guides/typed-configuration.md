# Typed configuration

**Goal:** one configuration source in, many small validated config objects out,
each injectable on its own.

A service should depend on `EmailConfig`, not on a 200-key `Settings` blob it
reads two fields from. The pattern: register a helper that validates one section
of the raw config into its own typed singleton.

## The helper

```python
def register_config_section(services, config_type: type, section: str):
    def factory(provider):
        raw = provider.resolve(RawConfig)
        return config_type.model_validate(getattr(raw, section))
    services.add_singleton(config_type, factory=factory)
```

`config_type` here is a Pydantic model (or anything with a classmethod that
takes a dict), and `section` names the attribute on the raw config to validate.
Substitute your own validation call if you are not using Pydantic.

## Using it

```python
services.add_singleton(RawConfig, instance=load_raw_config())

register_config_section(services, EmailConfig, "email")
register_config_section(services, StorageConfig, "storage")
register_config_section(services, RateLimitConfig, "rate_limits")
```

Now a service asks for exactly the slice it needs:

```python
class Mailer:
    def __init__(self, config: EmailConfig, http: AsyncClient):
        self._from = config.from_address
        self._http = http
```

`Mailer` gets a validated `EmailConfig`, not a dict, and not the whole config.
It cannot accidentally read `config.storage.bucket`.

## Why singletons

Each section is validated once, at `build_provider()`, so a malformed
`rate_limits` section fails startup rather than the first request that needs it.
The validated object is immutable config, safe to share.

## Environment branching

Registration is plain Python, so environment differences are an `if`:

```python
def build_container(env: str) -> ServiceProvider:
    services = ServiceCollection()
    services.add_singleton(RawConfig, instance=load_raw_config(env))
    register_config_section(services, EmailConfig, "email")

    if env == "prod":
        services.add_singleton(EmailSender, SesEmailSender)
        services.add_singleton(Cache, RedisCache)
    else:
        services.add_singleton(EmailSender, ConsoleEmailSender)
        services.add_singleton(Cache, InMemoryCache)

    return services.build_provider()
```

No `depi` feature is involved — it is a function that returns different
registrations.
