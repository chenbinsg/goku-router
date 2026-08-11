"""Pytest bootstrap — imports the app exactly as CI does: with no ``.env``.

``app/config.py`` builds ``Settings`` (and ``app/db.py`` its engine) at import
time, reading ``.env`` from the working directory. Nothing in the suite
overrode that, so on any machine that has a real ``.env`` — every developer
box, and the deployment host — ``pytest`` ran against the LIVE router database
and wrote into it: three consecutive runs left nine bogus
``workspace_guardrail_configs`` rows (including 80- and 180-char prompt limits)
in a working database. The same ``.env`` also replaced the credentials the
tests authenticate with, so ~22 of them failed with 401 for reasons that had
nothing to do with the code under test.

CI passes because a fresh checkout has no ``.env``. Reproducing that is enough
to fix both problems: import the app from a scratch directory so the file is
simply not found, and point the database at a throwaway SQLite file. The guard
below then refuses to run if anything still resolves to a server database — a
wrong answer here is silent data corruption, so it fails loudly rather than
proceeding.
"""

import os
import pathlib
import shutil
import tempfile

_TEST_DIR = pathlib.Path(tempfile.mkdtemp(prefix="goku-router-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DIR / 'test.db'}"

# Import the app with the repo's .env out of reach. Env vars still win over the
# (now absent) file, so DATABASE_URL above is what the engine binds to.
_ORIGINAL_CWD = os.getcwd()
os.chdir(_TEST_DIR)
try:
    from app.db import DATABASE_URL  # noqa: E402
finally:
    os.chdir(_ORIGINAL_CWD)

import pytest  # noqa: E402


def pytest_configure(config):
    if not DATABASE_URL.startswith("sqlite"):
        pytest.exit(
            f"Refusing to run: tests resolved DATABASE_URL to {DATABASE_URL!r}. "
            "The suite creates, mutates and deletes rows, so it must never point "
            "at a server database.",
            returncode=1,
        )


def pytest_unconfigure(config):
    shutil.rmtree(_TEST_DIR, ignore_errors=True)
