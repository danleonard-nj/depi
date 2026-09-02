# The dependency graph

`build_provider()` treats the registrations as a directed graph — an edge from
each type to each of its constructor dependencies — and checks it before
returning a provider. A problem here is a
[`RegistrationError`][depi.RegistrationError], raised at startup.

```python
provider = services.build_provider()   # validation happens here
```

## What is checked

### Missing dependencies

Every constructor parameter of every **singleton** must resolve to a
registration. A missing one raises
[`UnregisteredDependencyError`][depi.UnregisteredDependencyError] naming both the
missing type and the type that needed it:

```
Failed to locate registration for 'Config' while instantiating 'Database'
```

Missing dependencies of *transient* and *scoped* types are not failed at build
time — they surface as `UnregisteredDependencyError` on first resolve instead.

### Cycles

The whole graph is walked for cycles, across every lifetime. A cycle raises
[`CircularDependencyError`][depi.CircularDependencyError] with the chain:

```
Cyclic dependency detected: Order -> Invoice -> Customer -> Order
```

The message is trimmed to the cycle itself. A class that merely depends on a
loop without being part of it is not named. A self-referential class
(`A` needs `A`) is reported as `A -> A`.

Cycles are found by static analysis of constructor signatures. A cycle formed
through a [factory](factories.md) is not detected here and will recurse at
resolve time.

### Lifetime validation

A **singleton** may not have a constructor dependency that is **transient** or
**scoped**. Either raises [`InvalidLifetimeError`][depi.InvalidLifetimeError]:

```
Singleton 'ReportService' cannot depend on scoped 'UnitOfWork'.
Scoped dependencies would only be instantiated once during singleton creation,
breaking scope isolation.
```

This is checked transitively: `SingletonA -> SingletonB -> TransientC` fails,
because `SingletonB` cannot hold `TransientC`.

Not checked: a singleton registered by `factory=` that resolves a transient
inside the factory. `depi` cannot see into the factory, and the factory author
has taken responsibility. See [Factories](factories.md).

### Unknown lifetime

A registration carrying a lifetime string `depi` does not recognise raises
[`UnknownLifetimeError`][depi.UnknownLifetimeError] at resolve time. You only hit
this by constructing a `DependencyRegistration` by hand.

## Construction order

The strict pass also produces a dependency-first ordering of the singletons,
which is the order eager singletons and singleton factories are constructed in
during `build_provider()`. You do not interact with this directly; it is why a
singleton factory can `provider.resolve(...)` its own dependencies and get
finished objects.

## Cost

For a container of ~100 registrations four levels deep, `build_provider()` — the
whole validation and ordering pass — is a fraction of a millisecond, paid once
at startup. It does not grow with the number of *resolutions* the application
later performs. Exact figures depend on the machine; see the
[README benchmarks](https://github.com/danleonard-nj/depi#performance) and their
caveats.
