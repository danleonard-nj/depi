# pydepi-flask

Flask integration for [pydepi](https://github.com/danleonard-nj/depi), a type-hint driven dependency injection container.

This package contains only the Flask adapter. The container itself lives in `pydepi`, which has no dependencies of its own.

## Install

```bash
pip install pydepi-flask
```

The extras alias also works, though the name above is more accurate --
this is a separate distribution, not a feature of core:

```bash
pip install pydepi[flask]
```

## Use

```python
from depi_flask import FlaskInjector
```

See the [main README](https://github.com/danleonard-nj/depi#framework-integrations) for the full integration guide.
