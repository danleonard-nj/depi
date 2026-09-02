# pydepi-fastapi

FastAPI integration for [pydepi](https://github.com/danleonard-nj/depi), a type-hint driven dependency injection container.

This package contains only the FastAPI adapter. The container itself lives in `pydepi`, which has no dependencies of its own.

## Install

```bash
pip install pydepi-fastapi
```

The extras alias also works, though the name above is more accurate --
this is a separate distribution, not a feature of core:

```bash
pip install pydepi[fastapi]
```

## Use

```python
from depi_fastapi import FastAPIInjector
```

See the [main README](https://github.com/danleonard-nj/depi#framework-integrations) for the full integration guide.
