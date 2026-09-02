# Container

The registration API ([`ServiceCollection`][depi.ServiceCollection]), the built
container ([`ServiceProvider`][depi.ServiceProvider]), and the per-scope view
([`ServiceScope`][depi.ServiceScope]).

See [Registration](../concepts/registration.md), [Resolution](../concepts/resolution.md),
and [Lifetimes and scopes](../concepts/lifetimes-and-scopes.md) for the
narrative versions.

## ServiceCollection

::: depi.ServiceCollection

## ServiceProvider

::: depi.ServiceProvider

## ServiceScope

::: depi.ServiceScope

## Lifetime

::: depi.Lifetime

## Registration records

These describe a registration after it has been parsed. Application code rarely
touches them directly; they are public because factories and diagnostics can
read them.

::: depi.ConstructorDependency

::: depi.DependencyRegistration
