"""
Render tests/benchmarks.png from a pytest-benchmark JSON report.

Replaces a notebook that read a gitignored 50MB artifact, so the chart in the
README can actually be reproduced:

    pytest tests/benchmarks --benchmark-enable --benchmark-warmup=on \
        --benchmark-json=tests/benchmark_results.json
    python tests/plot_benchmarks.py tests/benchmark_results.json

Absolute timings move a lot with machine load -- runs on the same laptop have
differed by 50% -- so each panel is labelled with the ratio between the two
libraries as well. The ratio is the part that holds still.
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

# (title, depi benchmark, dependency-injector benchmark, unit, scale from seconds)
PANELS = [
    ('Simple resolution', 'test_depi_resolution', 'test_di_resolution', 'ns', 1e9),
    ('Complex resolution', 'test_depi_complex_resolution', 'test_di_complex_resolution', 'ns', 1e9),
    ('Container setup', 'test_depi_setup', 'test_di_setup', 'µs', 1e6),
    ('Memory allocation', 'test_depi_memory', 'test_di_memory', 'µs', 1e6),
]

DEPI_COLOUR = '#2f6f9f'
OTHER_COLOUR = '#b0b7bd'


def main(argv: list) -> int:
    report_path = Path(argv[1] if len(argv) > 1 else 'tests/benchmark_results.json')
    out_path = Path(argv[2] if len(argv) > 2 else 'tests/benchmarks.png')

    if not report_path.exists():
        print(f'no benchmark report at {report_path}; run pytest with '
              f'--benchmark-json first', file=sys.stderr)
        return 1

    report = json.loads(report_path.read_text(encoding='utf-8'))
    stats = {b['name']: b['stats'] for b in report['benchmarks']}

    missing = [n for _, a, b, _, _ in PANELS for n in (a, b) if n not in stats]
    if missing:
        print(f'report is missing benchmarks: {missing}', file=sys.stderr)
        return 1

    machine = report.get('machine_info', {})
    cpu = machine.get('cpu', {}).get('brand_raw', 'unknown CPU')
    python_version = machine.get('python_version', '?')

    fig, axes = plt.subplots(1, 4, figsize=(13, 3.8))

    for ax, (title, depi_key, other_key, unit, scale) in zip(axes, PANELS):
        depi = stats[depi_key]['mean'] * scale
        other = stats[other_key]['mean'] * scale

        bars = ax.bar(['depi', 'dependency-\ninjector'], [depi, other],
                      color=[DEPI_COLOUR, OTHER_COLOUR], width=0.6)
        ax.set_title(title, fontsize=10, pad=14)
        ax.set_ylabel(unit, fontsize=8)
        ax.tick_params(labelsize=8)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.set_ylim(0, max(depi, other) * 1.28)

        for bar, value in zip(bars, (depi, other)):
            ax.text(bar.get_x() + bar.get_width() / 2, value,
                    f'{value:,.1f}', ha='center', va='bottom', fontsize=8)

        # Say which way the comparison runs, so a shorter bar is never ambiguous.
        if depi <= other:
            note = f'depi {other / depi:.1f}x faster'
        else:
            note = f'depi {depi / other:.1f}x slower'
        ax.text(0.5, 0.94, note, transform=ax.transAxes, ha='center',
                va='top', fontsize=8, color='#555')

    fig.suptitle('depi vs dependency-injector — mean of pytest-benchmark rounds',
                 fontsize=11, y=1.0)
    fig.text(0.5, -0.04, f'{cpu} · Python {python_version} · '
                         f'absolute values are load-sensitive; ratios are the stable figure',
             ha='center', fontsize=7.5, color='#666')
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches='tight', facecolor='white')
    print(f'wrote {out_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
