# Concepts

The container has a small model. These pages describe each part of it, and only
the parts that exist in the implementation.

| Page | What it covers |
| --- | --- |
| [Registration](registration.md) | `ServiceCollection`, the `add_*` methods, registration by interface / instance / factory, the composition root |
| [Resolution](resolution.md) | `resolve` / `resolve_async`, construction order, how annotations are read |
| [Lifetimes and scopes](lifetimes-and-scopes.md) | singleton, transient, scoped; `create_scope`; the ambient scope contextvar |
| [Factories](factories.md) | `factory=`, what a factory receives, when it runs |
| [Async](async.md) | `resolve_async`, async factories, async scope exit |
| [Disposal](disposal.md) | what gets disposed, when, and what does not |
| [The dependency graph](dependency-graph.md) | build-time validation, cycle detection, lifetime rules |
| [Errors](errors.md) | the exception hierarchy and what raises each error |

If you have read [Getting started](../getting-started.md) you have already seen
registration, resolution, and lifetimes in use. These pages fill in the edges.
