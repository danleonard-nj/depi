"""
Assert that importing the core container pulls in no third-party code.

This is the guarantee most likely to regress silently: someone adds a
convenience import to depi/__init__.py, everything still passes locally because
the developer has every framework installed, and `pip install pydepi` quietly
starts dragging in Flask.

Run it in an environment where core is the only depi package installed:

    python scripts/check_core_purity.py
"""

import sys

# Modules that ship with CPython but are not imported by a clean interpreter,
# so they would otherwise look like third-party imports.
STDLIB_OK = {
    'abc', 'asyncio', 'collections', 'concurrent', 'contextlib', 'contextvars',
    'dataclasses', 'enum', 'functools', 'inspect', 'logging', 'threading',
    'types', 'typing', 'weakref',
}


def main() -> int:
    before = set(sys.modules)

    import depi  # noqa: F401

    added = set(sys.modules) - before
    roots = {name.split('.')[0] for name in added}

    # Anything not obviously stdlib and not depi itself is suspect. Rather than
    # maintain a stdlib allowlist by hand, lean on sys.stdlib_module_names.
    stdlib = set(getattr(sys, 'stdlib_module_names', ())) | STDLIB_OK
    foreign = sorted(r for r in roots if r not in stdlib and not r.startswith('_') and r != 'depi')

    if foreign:
        print('FAIL: importing depi pulled in third-party modules:', file=sys.stderr)
        for name in foreign:
            print(f'  - {name}', file=sys.stderr)
        print(
            '\nCore must stay dependency-free. Framework code belongs in an '
            'adapter package (pydepi-flask, pydepi-fastapi, ...).',
            file=sys.stderr,
        )
        return 1

    print(f'OK: `import depi` added {len(added)} modules, all stdlib.')

    # The adapters must not be reachable from core either -- if one is importable
    # here, the packages have started overlapping.
    for adapter in ('depi_flask', 'depi_quart', 'depi_fastapi', 'depi_django'):
        if adapter in sys.modules:
            print(f'FAIL: {adapter} was imported as a side effect of importing depi.',
                  file=sys.stderr)
            return 1

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
