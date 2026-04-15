"""Very small coverage helper using the standard-library trace module."""

from __future__ import annotations

import ast
import pathlib
import sys
import trace
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PACKAGE_ROOT = SRC / "lumentp"
TRACE_DIR = ROOT / "trace_output"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def executable_lines(path: pathlib.Path) -> set[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.stmt) and hasattr(node, "lineno")
    }


def discover_and_run_tests() -> unittest.result.TestResult:
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    return unittest.TextTestRunner(verbosity=1).run(suite)


def main() -> int:
    tracer = trace.Trace(count=True, trace=False)
    result = tracer.runfunc(discover_and_run_tests)
    results = tracer.results()
    TRACE_DIR.mkdir(exist_ok=True)
    results.write_results(show_missing=True, coverdir=str(TRACE_DIR))

    total_lines = 0
    covered_lines = 0
    counts = results.counts

    for path in PACKAGE_ROOT.glob("*.py"):
        relevant = executable_lines(path)
        total_lines += len(relevant)
        for line in relevant:
            if counts.get((str(path), line), 0) > 0:
                covered_lines += 1

    percent = (covered_lines / total_lines * 100.0) if total_lines else 0.0
    print(f"Measured statement coverage for src/lumentp: {covered_lines}/{total_lines} = {percent:.2f}%")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
