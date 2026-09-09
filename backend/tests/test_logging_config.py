import logging

import pytest

from app.logging_config import RoutineAccessFilter, setup_logging


@pytest.mark.parametrize("path,status", [
    ("/health", 200), ("/health?probe=ready", 200), ("/", 307),
    ("/console", 200), ("/console/", 200),
    ("/console/assets/app.js?v=1", 200), ("/console/assets/app.css", 304),
])
@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_routine_access_is_suppressed(path, status, method):
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, "%s %s %s %s %s",
                               ("client", method, path, "1.1", status), None)
    assert not RoutineAccessFilter().filter(record)


@pytest.mark.parametrize("path,status,method", [
    ("/health", 503, "GET"), ("/", 500, "GET"), ("/", 404, "GET"),
    ("/", 200, "GET"), ("/console/", 401, "GET"),
    ("/console/assets/app.js", 404, "GET"), ("/console/", 500, "GET"),
    ("/v1/chat/completions", 200, "POST"), ("/admin/logs", 200, "GET"),
    ("/console/assets-other", 200, "GET"), ("/health", 200, "POST"),
    ("/console/", 200, "OPTIONS"),
])
def test_other_access_is_preserved(path, status, method):
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, "%s %s %s %s %s",
                               ("client", method, path, "1.1", status), None)
    assert RoutineAccessFilter().filter(record)


def test_text_logging_installs_filter_once(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "text")
    logger = logging.getLogger("uvicorn.access")
    original_filters = logger.filters[:]
    try:
        logger.filters = []
        setup_logging()
        setup_logging()
        assert len(logger.filters) == 1
        assert isinstance(logger.filters[0], RoutineAccessFilter)
    finally:
        logger.filters = original_filters
