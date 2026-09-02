# 2. The application service

> File: `shortlinks/service.py`

The application layer holds the use cases. It imports the domain and nothing
else. Each use case is a class that takes its dependencies as constructor
parameters, typed as the domain interfaces from [step 1](1-the-domain.md).

```python
# shortlinks/service.py
from shortlinks.domain import Clock, CodeGenerator, Link, LinkRepository


class UnknownCode(Exception):
    """Raised by FollowLink when no link has the given code."""


class CreateLink:
    def __init__(self, links: LinkRepository, codes: CodeGenerator, clock: Clock):
        self._links = links
        self._codes = codes
        self._clock = clock

    def __call__(self, target: str) -> Link:
        code = self._codes.next()
        while self._links.by_code(code) is not None:   # avoid a collision
            code = self._codes.next()
        link = Link(code=code, target=target, created_at=self._clock.now_iso())
        self._links.add(link)
        return link


class FollowLink:
    def __init__(self, links: LinkRepository):
        self._links = links

    def __call__(self, code: str) -> str:
        link = self._links.by_code(code)
        if link is None:
            raise UnknownCode(code)
        self._links.record_hit(code)
        return link.target
```

`CreateLink` and `FollowLink` are callables — `__init__` takes the
collaborators, `__call__` does one job. They know nothing about how a
`LinkRepository` stores data or where `CodeGenerator` gets its codes.

## Test it without a container

Because these are plain classes, a test just constructs them with fakes:

```python
# tests/test_service.py
from shortlinks.domain import Link
from shortlinks.service import CreateLink, FollowLink, UnknownCode


class DictRepo:
    def __init__(self):
        self._rows: dict[str, Link] = {}
    def add(self, link): self._rows[link.code] = link
    def by_code(self, code): return self._rows.get(code)
    def record_hit(self, code):
        if code in self._rows:
            self._rows[code].hits += 1


class SequenceCodes:
    def __init__(self, *codes): self._it = iter(codes)
    def next(self): return next(self._it)


class FixedClock:
    def now_iso(self): return "2020-01-01T00:00:00+00:00"


def test_create_then_follow():
    repo = DictRepo()
    link = CreateLink(repo, SequenceCodes("abc123"), FixedClock())("https://example.com")

    assert link.code == "abc123"
    assert link.created_at == "2020-01-01T00:00:00+00:00"
    assert FollowLink(repo)("abc123") == "https://example.com"


def test_unknown_code_raises():
    import pytest
    with pytest.raises(UnknownCode):
        FollowLink(DictRepo())("missing")
```

No `depi` here. That is the point of taking dependencies as constructor
parameters — the use case is testable with three throwaway classes and no
wiring.

## Checkpoint

```bash
pytest tests/test_service.py -q
# 2 passed
```

Next: real implementations of those three interfaces, and a container to wire
them.
