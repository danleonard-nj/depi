@echo off
REM Run from the repository root, not from tests/.
pytest tests/benchmarks --benchmark-enable --benchmark-warmup=on --benchmark-json=tests/benchmark_results.json
