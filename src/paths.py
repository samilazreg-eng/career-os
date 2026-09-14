# paths.py

import os
from pathlib import Path


CAREER_OS_DIR = Path(__file__).resolve().parent.parent

CAREER_DIR_NAME = ".career"
HEAD_FILE_NAME = "HEAD.json"


def discover_repo_dir(start: Path) -> Path | None:
    """
    @brief Walk upward from `start` looking for an initialized Career
           repository, the same way `git` discovers the nearest '.git'.

    @param start Physical directory to begin the search from.

    @return The nearest ancestor (including `start`) that is a Career
            repository root, or None if none was found.
    """
    for candidate in (start, *start.parents):
        if (candidate / CAREER_DIR_NAME / HEAD_FILE_NAME).is_file():
            return candidate

    return None


def resolve_repo_dir() -> Path:
    """
    @brief Resolve the Career repository that the current process operates
           on.

    @details
    Like `git`, Career has no single global repository: each directory can
    become its own independent repository via 'career init', and every
    other command operates on the nearest repository found by walking up
    from the current working directory.

    'CAREER_REPO_DIR' pins the repository explicitly, bypassing discovery
    (primarily for tests and scripting).

    @return Absolute physical directory of the active Career repository, or
            the current working directory if no repository is found yet
            (e.g. the target of a not-yet-run 'career init').
    """
    override = os.environ.get("CAREER_REPO_DIR")
    if override:
        return Path(override).resolve()

    cwd = Path.cwd().resolve()

    return discover_repo_dir(cwd) or cwd


REPO_DIR = resolve_repo_dir()

HEAD_FILE = REPO_DIR / CAREER_DIR_NAME / HEAD_FILE_NAME