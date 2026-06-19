"""Code chunking: extract function- and class-level chunks from a Python repo.

Strategy
--------
For each ``.py`` file:
1. Parse with ``ast``.
2. Extract every top-level and class-nested ``FunctionDef``, ``AsyncFunctionDef``,
   and ``ClassDef`` as its own chunk (qualified name: ``ClassName.method_name``).
3. If the file fails to parse (``SyntaxError``), log a warning and fall back
   to treating the whole file as one chunk.
4. If the file parses successfully but contains no functions or classes (e.g. an
   ``__init__.py`` with only imports), also fall back to a whole-file chunk.

Directories named ``.git``, ``__pycache__``, ``venv``, ``.venv``, ``node_modules``
and any directory whose name starts with ``.`` are excluded from the walk.
"""

import ast
import logging
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)

_SKIP_DIRS: frozenset[str] = frozenset(
    {".git", "__pycache__", "venv", ".venv", "node_modules"}
)


# ---------------------------------------------------------------------------
# Public data model
# ---------------------------------------------------------------------------


class CodeChunk(BaseModel):
    """A single extracted code chunk ready to be embedded and stored."""

    file_path: str
    symbol_name: str | None  # e.g. "MyClass.my_method"; None for whole-file chunks
    content: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_skipped(parts: tuple[str, ...]) -> bool:
    """Return True if any path component indicates a directory to skip."""
    return any(part in _SKIP_DIRS or part.startswith(".") for part in parts)


def _collect_py_files(repo_root: Path) -> list[Path]:
    """Return all ``.py`` files under *repo_root*, excluding noise directories."""
    result: list[Path] = []
    for path in repo_root.rglob("*.py"):
        rel_parts = path.relative_to(repo_root).parts
        # Exclude filename (last part) from the dir-skip check.
        if _is_skipped(rel_parts[:-1]):
            continue
        result.append(path)
    return sorted(result)  # deterministic order


def _qualified(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef, parent: str | None
) -> str:
    return f"{parent}.{node.name}" if parent else node.name


def _extract_symbols(
    source: str,
    tree: ast.Module,
    rel_path: str,
) -> list[CodeChunk]:
    """Walk *tree* and return one chunk per FunctionDef/AsyncFunctionDef/ClassDef.

    Recurses into class bodies to capture methods.  Does not recurse into
    nested function bodies (inner functions add retrieval noise).
    """
    chunks: list[CodeChunk] = []

    def _visit(node: ast.AST, parent: str | None = None) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            qname = _qualified(node, parent)  # type: ignore[arg-type]
            segment = ast.get_source_segment(source, node)
            if segment:
                chunks.append(
                    CodeChunk(file_path=rel_path, symbol_name=qname, content=segment)
                )
            if isinstance(node, ast.ClassDef):
                for child in ast.iter_child_nodes(node):
                    _visit(child, parent=qname)
        elif isinstance(node, ast.Module):
            for child in ast.iter_child_nodes(node):
                _visit(child)

    _visit(tree)
    return chunks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def chunk_repo(repo_root: Path) -> list[CodeChunk]:
    """Walk *repo_root*, chunk every ``.py`` file, and return all chunks.

    Per-file behaviour:
    - Parse failure (``SyntaxError``) → log warning, use whole-file chunk.
    - No top-level symbols found → use whole-file chunk.
    - Empty file → skip.
    """
    py_files = _collect_py_files(repo_root)
    all_chunks: list[CodeChunk] = []

    for py_file in py_files:
        rel_path = str(py_file.relative_to(repo_root))
        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning(
                "Cannot read file — skipping",
                extra={"path": rel_path, "error": str(exc)},
            )
            continue

        if not source.strip():
            continue

        try:
            tree = ast.parse(source)
        except SyntaxError:
            logger.warning(
                "Syntax error — falling back to whole-file chunk",
                extra={"path": rel_path},
            )
            all_chunks.append(
                CodeChunk(file_path=rel_path, symbol_name=None, content=source)
            )
            continue

        symbols = _extract_symbols(source, tree, rel_path)
        if symbols:
            all_chunks.extend(symbols)
        else:
            # File parsed cleanly but has no functions/classes (e.g. pure imports).
            all_chunks.append(
                CodeChunk(file_path=rel_path, symbol_name=None, content=source)
            )

    return all_chunks
