"""
Fail if any package source file is excluded by .gitignore.

A bare pattern in .gitignore matches at every depth, so a line like
``exceptions.py`` — intended for a scratch file at the repo root — silently
excluded ``packages/depi-core/depi/exceptions.py``. Everything passed locally,
because the file was on disk and setuptools builds from the filesystem rather
than from git. It would have broken on the next fresh clone.

CI does eventually catch this, as an ImportError somewhere unhelpful. This
catches it here, with a message that says what is wrong.

    python scripts/check_sources_tracked.py
"""

import subprocess
import sys


def main() -> int:
    result = subprocess.run(
        ['git', 'ls-files', '--others', '--ignored', '--exclude-standard',
         '--', 'packages/*.py', 'scripts/*.py', 'tests/*.py'],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f'git ls-files failed: {result.stderr.strip()}', file=sys.stderr)
        return 1

    ignored = [line for line in result.stdout.splitlines() if line.strip()]
    if ignored:
        print('FAIL: these source files are excluded by .gitignore:', file=sys.stderr)
        for path in ignored:
            print(f'  - {path}', file=sys.stderr)
        print(
            '\nThey exist on disk, so tests and builds pass here, but they are not '
            'in the repository and will be missing from a fresh clone.\n'
            'Check .gitignore for an unanchored filename pattern: prefix it with '
            '"/" to limit it to the repository root.',
            file=sys.stderr,
        )
        return 1

    print('OK: no package sources are excluded by .gitignore.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
