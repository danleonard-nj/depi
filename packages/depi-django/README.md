# pydepi-django

Django integration for [pydepi](https://github.com/danleonard-nj/depi), a type-hint driven dependency injection container.

This package contains only the Django adapter. The container itself lives in `pydepi`, which has no dependencies of its own.

## Install

```bash
pip install pydepi-django
```

The extras alias also works, though the name above is more accurate --
this is a separate distribution, not a feature of core:

```bash
pip install pydepi[django]
```

## Use

```python
from depi_django import DjangoInjector
```

See the [Django integration guide](https://danleonard-nj.github.io/depi/integrations/django/) for the full walkthrough.
