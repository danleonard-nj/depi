# FastAPI adapter

`pip install pydepi-fastapi` — import as `depi_fastapi`. Usage guide:
[FastAPI integration](../integrations/fastapi.md).

`autowire=True` is rejected at construction and `inject` raises
`NotImplementedError`; resolve from the scope returned by `get_scope` instead.

::: depi_fastapi.FastAPIInjector
    options:
      inherited_members: true
