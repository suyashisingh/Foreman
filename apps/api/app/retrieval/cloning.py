"""Git repository cloning utilities.

Clones repos into a per-repo directory under ``settings.REPO_CLONE_DIR``
using GitPython with depth=1 (current snapshot only, no history).
"""

import logging
import shutil
from pathlib import Path

import git

from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Typed exceptions
# ---------------------------------------------------------------------------


class CloneError(RuntimeError):
    """Raised when a repository clone operation fails for any reason."""


class CloneAuthError(CloneError):
    """Raised when git reports an authentication / authorisation failure."""


class CloneTimeoutError(CloneError):
    """Raised when the clone operation exceeds the allowed time."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def clone_repo(clone_url: str, repo_id: str) -> Path:
    """Clone *clone_url* (shallow, depth=1) into ``REPO_CLONE_DIR/<repo_id>``.

    Returns the ``Path`` to the cloned directory on success.
    Removes any leftover directory from a previous failed attempt before
    starting so this function is safe to call on retry.

    Raises:
        CloneAuthError: Authentication / permission failure reported by git.
        CloneTimeoutError: The clone operation timed out.
        CloneError: Any other git failure.
    """
    clone_base = Path(settings.REPO_CLONE_DIR)
    clone_base.mkdir(parents=True, exist_ok=True)
    dest = clone_base / repo_id

    if dest.exists():
        shutil.rmtree(dest)

    logger.info("Cloning repository", extra={"url": clone_url, "dest": str(dest)})
    try:
        git.Repo.clone_from(clone_url, dest, depth=1, no_single_branch=False)
    except git.exc.GitCommandNotFound as exc:  # type: ignore[attr-defined]
        raise CloneError("git executable not found on PATH") from exc
    except git.exc.GitCommandError as exc:  # type: ignore[attr-defined]
        stderr = str(exc.stderr or "")
        if any(
            kw in stderr
            for kw in ("Authentication failed", "could not read Username", "403")
        ):
            raise CloneAuthError(
                f"Authentication failed for {clone_url!r}: {stderr}"
            ) from exc
        if any(kw in stderr.lower() for kw in ("timeout", "timed out")):
            raise CloneTimeoutError(f"Clone timed out for {clone_url!r}") from exc
        raise CloneError(f"Clone failed for {clone_url!r}: {stderr}") from exc
    except Exception as exc:
        raise CloneError(f"Unexpected error cloning {clone_url!r}: {exc}") from exc

    logger.info("Clone complete", extra={"dest": str(dest)})
    return dest


def remove_clone(repo_id: str) -> None:
    """Delete the cloned directory for *repo_id* if it exists.

    Safe to call even when cloning never completed.
    """
    dest = Path(settings.REPO_CLONE_DIR) / repo_id
    if dest.exists():
        shutil.rmtree(dest)
        logger.debug("Removed clone directory", extra={"dest": str(dest)})
