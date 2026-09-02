# Guides

Task-oriented answers to "how do I...". Each guide assumes the
[Concepts](../concepts/index.md) and shows a concrete pattern rather than
re-explaining the API.

- **[Testing with replacement dependencies](testing.md)** — swap infrastructure
  for fakes without touching application code.
- **[Async dependencies](async-dependencies.md)** — async factories, awaiting
  cleanup, resolving under an async web framework.
- **[Third-party clients and factories](third-party-clients.md)** — wrap SDK
  clients that have no annotated constructor.
- **[Typed configuration](typed-configuration.md)** — turn one config object
  into many validated, injectable sections.
- **[Organizing a large container](organizing-registrations.md)** — split
  registration by role so the composition root stays readable.
- **[Handling errors at startup](error-handling.md)** — make wiring mistakes
  fail the process, not a request.
- **[Releasing resources](resource-teardown.md)** — dispose scoped resources;
  handle process-wide ones yourself.
