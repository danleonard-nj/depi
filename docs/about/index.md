# About

## Why it exists

In an application with many collaborators, construction code tends to spread
across request handlers, module globals, and test fixtures. A constructor change
then touches every copy of that wiring. `depi` centralizes those choices and
derives construction order from type annotations.

Its vocabulary follows .NET's `Microsoft.Extensions.DependencyInjection`:
`ServiceCollection`, `ServiceProvider`, and singleton, scoped, and transient
lifetimes. The implementation is Python-native: registrations are ordinary
Python, and the core has no third-party runtime dependencies.

## Design choices

- **Annotations describe dependencies.** Application classes need no base class,
  decorator, generated binding, or separate configuration language.
- **Validation precedes use where possible.** `build_provider()` detects cycles,
  invalid singleton dependencies, and missing singleton dependencies. Some
  missing scoped or transient dependencies remain resolve-time errors; see
  [Limitations](limitations.md).
- **Framework code stays optional.** Flask, Quart, FastAPI, and Django adapters
  are separate distributions. The same services can run from a CLI or worker.
- **Resolution follows the requested subgraph.** Container size does not make an
  unrelated shallow resolution walk every registration. Graph validation is a
  one-time build cost.
- **Compatibility is explicit.** Typed DEPI exceptions retain the base exception
  types used by earlier releases so existing handlers continue to catch them.

How to keep wiring separate from application behavior is covered once, in
[Architecture](../architecture/index.md).

## Provenance and maturity

The design has been developed since 2020. Its predecessor,
[`framework/di`](https://github.com/danleonard-nj/framework/tree/main/framework/di),
has run in a production service since 2022 with more than 120 registrations in
one container. This repository separated that work into the dependency-free core
and independently released framework adapters.

The current packages are version 0.1.0 and marked Beta. That label should guide
upgrade expectations even though the underlying design predates the packaging.
Current behavioral boundaries are listed under [Limitations and
non-goals](limitations.md).
