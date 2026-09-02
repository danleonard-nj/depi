# Integration base

`depi.integration` is the contract every framework adapter is built on. It lives
in core and stays dependency-free. You only need this page if you are writing a
new adapter; for using the existing ones see [Integrations](../integrations/index.md).

An adapter subclasses [`BaseInjector`][depi.integration.BaseInjector] and
implements `setup(app)` to open a [`ServiceScope`][depi.ServiceScope] per
request, bind it with [`set_current_scope`][depi.set_current_scope], and dispose
it when the request ends.

::: depi.integration.BaseInjector

::: depi.integration.injectable_parameters
