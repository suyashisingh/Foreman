"""Curated benchmark task definitions.

Each task targets a small, well-tested public Python library and asks the
agent to add a clearly scoped method or function.  Success is measured by
the repo's own pytest suite (plus any tests the agent writes).

Repos chosen for:
  - Small size (fast clone, fast test runs inside E2B sandbox)
  - Comprehensive existing test suite
  - Clear, unambiguous correctness criteria
  - Variety of codebases so we don't optimise for a single layout

Difficulty is noted per-task (easy / medium / hard) so the benchmark
produces a meaningful spread rather than all-pass or all-fail.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BenchmarkTask:
    task_id: str
    repo_name: str
    clone_url: str
    default_branch: str
    issue_text: str
    difficulty: str  # "easy" | "medium" | "hard"


TASKS: list[BenchmarkTask] = [
    # ------------------------------------------------------------------
    # iniconfig — ~250 lines, minimal deps, proven in live testing
    # ------------------------------------------------------------------
    BenchmarkTask(
        task_id="iniconfig-get-default",
        repo_name="iniconfig",
        clone_url="https://github.com/pytest-dev/iniconfig.git",
        default_branch="main",
        issue_text=(
            "Add a `get(section: str, key: str, default: object = None)` method to "
            "the `IniConfig` class in `src/iniconfig/__init__.py`. It should return "
            "the value for `key` in `section` if it exists, or `default` when the key "
            "is absent — unlike the existing `__getitem__` it must never raise "
            "`KeyError`. Add tests in `testing/test_iniconfig.py`."
        ),
        difficulty="easy",
    ),
    BenchmarkTask(
        task_id="iniconfig-as-dict",
        repo_name="iniconfig",
        clone_url="https://github.com/pytest-dev/iniconfig.git",
        default_branch="main",
        issue_text=(
            "Add an `as_dict()` method to the `IniConfig` class in "
            "`src/iniconfig/__init__.py`. It should return the entire config as a "
            "plain Python `dict[str, dict[str, str]]` where each top-level key is a "
            "section name and the value is a dict of that section's key-value pairs. "
            "Add tests in `testing/test_iniconfig.py`."
        ),
        difficulty="easy",
    ),
    BenchmarkTask(
        task_id="iniconfig-section-names",
        repo_name="iniconfig",
        clone_url="https://github.com/pytest-dev/iniconfig.git",
        default_branch="main",
        issue_text=(
            "Add two methods to the `IniConfig` class in `src/iniconfig/__init__.py`: "
            "(1) `section_names() -> list[str]` returning a sorted list of all "
            "section names in the config; "
            "(2) `has_section(name: str) -> bool` returning True if the section "
            "exists. "
            "Add tests for both methods in `testing/test_iniconfig.py`."
        ),
        difficulty="easy",
    ),
    # ------------------------------------------------------------------
    # humanize — ~800 lines across 8 modules, well-maintained
    # ------------------------------------------------------------------
    BenchmarkTask(
        task_id="humanize-metric",
        repo_name="humanize",
        clone_url="https://github.com/python-humanize/humanize.git",
        default_branch="main",
        issue_text=(
            "Add a `metric(value: float, unit: str = '') -> str` function to "
            "`src/humanize/number.py` that formats a numeric value using SI metric "
            "prefixes: T (1e12), G (1e9), M (1e6), k (1e3), m (1e-3), μ (1e-6), "
            "n (1e-9). Values between 1 and 1000 (exclusive) use no prefix. "
            "Format to 2 decimal places; e.g. `metric(1500)` → `'1.50 k'`, "
            "`metric(0.001, 'Hz')` → `'1.00 mHz'`. "
            "Export `metric` from `src/humanize/__init__.py`. "
            "Add tests in `tests/test_number.py`."
        ),
        difficulty="medium",
    ),
    BenchmarkTask(
        task_id="humanize-clamp",
        repo_name="humanize",
        clone_url="https://github.com/python-humanize/humanize.git",
        default_branch="main",
        issue_text=(
            "Add a `clamp(value: float, min_value: float = 0, "
            "max_value: float = 100) -> float` function to "
            "`src/humanize/number.py` that clips `value` to the closed interval "
            "[min_value, max_value]. Raise `ValueError` if `min_value > max_value`. "
            "Export `clamp` from `src/humanize/__init__.py`. "
            "Add tests in `tests/test_number.py`."
        ),
        difficulty="easy",
    ),
    # ------------------------------------------------------------------
    # sortedcontainers — clear sorted data-structure library
    # ------------------------------------------------------------------
    BenchmarkTask(
        task_id="sortedcontainers-median",
        repo_name="sortedcontainers",
        clone_url="https://github.com/grantjenks/python-sortedcontainers.git",
        default_branch="main",
        issue_text=(
            "Add a `median()` method to the `SortedList` class in "
            "`src/sortedcontainers/sortedlist.py`. For an odd-length list return the "
            "middle element; for an even-length list return the arithmetic mean of the "
            "two central elements as a `float`. Raise `IndexError` with the message "
            "'median of empty sequence' when the list is empty. "
            "Add tests in `tests/test_sortedlist.py`."
        ),
        difficulty="medium",
    ),
    # ------------------------------------------------------------------
    # tabulate — table-formatting utility, single large module
    # ------------------------------------------------------------------
    BenchmarkTask(
        task_id="tabulate-column-count",
        repo_name="python-tabulate",
        clone_url="https://github.com/astanin/python-tabulate.git",
        default_branch="master",
        issue_text=(
            "Add a module-level `column_count(tabular_data: object) -> int` function "
            "to `tabulate/tabulate.py` (also export it from `tabulate/__init__.py`). "
            "It must return the number of columns for: a list of lists (len of first "
            "row), a list of dicts (number of keys in first dict). "
            "Raise `ValueError` if `tabular_data` is empty or the first row is empty. "
            "Add tests in `test/test_regression.py`."
        ),
        difficulty="medium",
    ),
    # ------------------------------------------------------------------
    # natsort — natural-sort key library
    # ------------------------------------------------------------------
    BenchmarkTask(
        task_id="natsort-keygen-reversed",
        repo_name="natsort",
        clone_url="https://github.com/SethMMorton/natsort.git",
        default_branch="master",
        issue_text=(
            "Add a `natsort_keygen_reversed(alg=ns.DEFAULT)` convenience function to "
            "`natsort/natsort.py` that returns a key function equivalent to "
            "`natsort_keygen(alg=alg | ns.REVERSE)`, making it easy to pass a "
            "reverse-natural-sort key directly to `sorted()`. "
            "Export `natsort_keygen_reversed` from `natsort/__init__.py`. "
            "Add tests in `tests/test_natsort.py`."
        ),
        difficulty="hard",
    ),
]

TASK_MAP: dict[str, BenchmarkTask] = {t.task_id: t for t in TASKS}
