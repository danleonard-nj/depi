# 1. The domain

> File: `shortlinks/domain.py`

For this application, `domain.py` holds the entity and three small interfaces.
This is the tutorial's chosen layout, not a structure required by `depi`.

```python
# shortlinks/domain.py
from dataclasses import dataclass
from typing import Protocol


@dataclass
class Link:
    code: str
    target: str
    created_at: str
    hits: int = 0


class LinkRepository(Protocol):
    def add(self, link: Link) -> None: ...
    def by_code(self, code: str) -> Link | None: ...
    def record_hit(self, code: str) -> None: ...


class CodeGenerator(Protocol):
    def next(self) -> str: ...


class Clock(Protocol):
    def now_iso(self) -> str: ...
```

## What each piece is

- **`Link`** — the entity. A plain dataclass; it has no behaviour that depends
  on anything external.
- **`LinkRepository`** — how the application stores and retrieves links. A
  `Protocol`, so any class with these three methods satisfies it. The real
  implementation (a database, an in-memory dict) comes in
  [step 3](3-wiring.md).
- **`CodeGenerator`** — produces a short code. Separated out because the
  application should not care *how* codes are generated (random, sequential, a
  hash) and tests will want to control it.
- **`Clock`** — reading the current time is an external dependency like any
  other. Injecting it keeps the application deterministic under test.

These `Protocol` classes are application types. In step 3 they become
registration keys, but `depi` does not require protocols.

## Checkpoint

Nothing to run yet, but the module imports cleanly:

```bash
python -c "import shortlinks.domain; print(shortlinks.domain.Link('x', 'y', 'z'))"
# Link(code='x', target='y', created_at='z', hits=0)
```

Next: the logic that uses these interfaces.
