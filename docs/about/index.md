# Design philosophy

## Why it exists

The recurring problem `depi` grew out of: in an application with many
collaborating objects, the code that constructs them spreads. "Which concrete
class, built with which arguments, shared or new" ends up inline in request
handlers, in module globals, in test fixtures that each rebuild a slightly
different graph. Adding a constructor parameter means editing every place that
builds the object. A container removes that by centralising construction: each
type is described once, and the container works out the rest from the
annotations.

The model is taken from .NET's
`Microsoft.Extensions.DependencyInjection` — `ServiceCollection`,
`ServiceProvider`, and the singleton / scoped / transient split. That design
works and is familiar to a large number of developers, so there was no reason to
invent a different vocabulary.

## Why framework independence matters

An application outlives the framework it was first built on, and is often
exercised from more than one entry point — an HTTP server, a queue consumer, a
CLI, a test suite. If the wiring is expressed in framework terms — endpoints
with injected markers, services that only resolve inside a request — every one
of those entry points has to carry the framework, and swapping the framework is
a rewrite.

`depi` keeps the framework at the edge. The four
[integrations](../integrations/index.md) are thin: they open a scope per
request, bind it, dispose it. Application and domain code never imports `depi`
or the framework, so the same service graph runs unchanged under Flask, a
worker, or a test.

## Why the container stays at the composition boundary

A container that application code imports — where domain methods call
`resolve()`, where a business rule only runs inside a scope — has stopped being
a convenience and become the architecture. The code can no longer be read,
tested, or reused without it.

So `depi` is built to be used from two places only: the
[composition root](../concepts/registration.md#the-composition-root), where
registration happens, and the framework adapter at the HTTP boundary, which
resolves the entry point for each request. Everything else receives its
dependencies as constructor parameters. The [Architecture](../architecture/index.md)
chapter demonstrates this and marks the exact line where `depi` stops being
imported.

This is a usage discipline, not something the library enforces — `ServiceProvider`
will happily be passed around and called from anywhere. The documentation, the
API shape (resolution is a method on the provider, not a global), and the
integration design all push toward keeping it at the edge.

## Design principles the code follows

- **Read wiring from annotations, not configuration.** A constructor parameter's
  type annotation is the single source of what it needs. No decorators on
  application classes, no separate binding DSL.
- **Fail at startup, not at request time.** `build_provider()` validates the
  whole graph — missing dependencies, cycles, lifetime violations — so a wiring
  bug stops the process rather than serving a 500.
- **Cost tracks depth, not size.** Resolution walks the sub-graph of what was
  asked for. A hundred-registration container resolves a shallow dependency as
  fast as a three-registration one.
- **Core carries no dependencies.** `pip install pydepi` pulls in nothing. Each
  framework adapter is a separate distribution with its own version, so a
  framework release that breaks an adapter cannot force a core release or drag a
  web framework into an application that only wanted the container.
- **Keep backwards compatibility within a major version.** The typed exception
  hierarchy still derives from the `Exception` / `RuntimeError` types it
  previously raised, so old handlers keep working.

## Provenance

The container has been in iterative development since 2020. A predecessor of the
same design — [`framework/di`](https://github.com/danleonard-nj/framework/tree/main/framework/di)
— has run in a production service since 2022, wiring 120+ registrations from one
container. The distributions in this repository are a restructure of that work
into independently released packages; their current status is on the
[Limitations](limitations.md#maturity) page.
