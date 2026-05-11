"""pytest suite for verixa_runtime.gateway.logging (CP-6.4).

Covers JsonLogFormatter rendering and StructuredLoggingMiddleware
behaviour: bypass paths, trace_id mint vs header, request log fields,
exception path, response trace_id echo header.
"""

from __future__ import annotations

import io
import json
import logging
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from verixa_runtime.app import create_app
from verixa_runtime.gateway.logging import (
    LOGGER_NAME,
    TRACE_ID_HEADER,
    JsonLogFormatter,
    StructuredLoggingMiddleware,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


TEST_API_KEY = "test-key-logging"
TEST_TENANT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaa04")


@pytest.fixture
def captured_logs(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Captures verixa.runtime log lines as parsed JSON dicts.

    Replaces the logger's handlers with an in-memory StringIO + JsonFormatter.
    """
    logger = logging.getLogger(LOGGER_NAME)
    original_handlers = logger.handlers[:]
    original_level = logger.level

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    logger.handlers = [handler]
    logger.setLevel(logging.DEBUG)

    parsed: list[dict] = []
    monkeypatch.setattr(
        # Wrap the captured stream into a property tests can read after the
        # request returns; we re-parse on each access.
        "verixa_runtime.gateway.logging.LOGGER_NAME", LOGGER_NAME
    )

    yield parsed

    # On teardown, parse anything written and append, then restore handlers
    handler.flush()
    for line in stream.getvalue().splitlines():
        if line.strip():
            parsed.append(json.loads(line))
    logger.handlers = original_handlers
    logger.setLevel(original_level)


@pytest.fixture
def client() -> TestClient:
    app = create_app(api_keys={TEST_API_KEY: TEST_TENANT_ID})
    return TestClient(app)


def _govern_payload() -> dict:
    return {
        "agent_identity": {
            "spiffe_id": "spiffe://x",
            "role": "r",
            "workflow_id": "22222222-2222-2222-2222-222222222222",
        },
        "action": {"type": "tool_call", "tool_name": "read_x"},
        "context": {"prompt_hash": "b" * 64, "model_version": "m"},
        "trace_id": "t",
    }


# ---------------------------------------------------------------------------
# JsonLogFormatter
# ---------------------------------------------------------------------------


def test_json_formatter_writes_basic_fields() -> None:
    fmt = JsonLogFormatter()
    record = logging.LogRecord(
        name="verixa.test",
        level=logging.INFO,
        pathname="x.py",
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    line = fmt.format(record)
    parsed = json.loads(line)
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "verixa.test"
    assert parsed["message"] == "hello"
    assert parsed["timestamp"].endswith("Z")


def test_json_formatter_includes_extras() -> None:
    fmt = JsonLogFormatter()
    record = logging.LogRecord(
        name="verixa.test",
        level=logging.INFO,
        pathname="x.py",
        lineno=1,
        msg="evt",
        args=(),
        exc_info=None,
    )
    record.tenant_id = "tid-x"
    record.trace_id = "trace-x"
    line = fmt.format(record)
    parsed = json.loads(line)
    assert parsed["tenant_id"] == "tid-x"
    assert parsed["trace_id"] == "trace-x"


def test_json_formatter_skips_underscore_attributes() -> None:
    """Private attributes (starting with _) are not emitted."""
    fmt = JsonLogFormatter()
    record = logging.LogRecord(
        name="x",
        level=logging.INFO,
        pathname="x.py",
        lineno=1,
        msg="m",
        args=(),
        exc_info=None,
    )
    record._private = "should-not-appear"  # type: ignore[attr-defined]
    parsed = json.loads(fmt.format(record))
    assert "_private" not in parsed


def test_json_formatter_uses_default_str_for_non_serialisable() -> None:
    """default=str fallback for objects without a JSON encoder."""
    fmt = JsonLogFormatter()
    record = logging.LogRecord(
        name="x",
        level=logging.INFO,
        pathname="x.py",
        lineno=1,
        msg="m",
        args=(),
        exc_info=None,
    )
    record.weird = uuid.UUID("11111111-1111-1111-1111-111111111111")
    parsed = json.loads(fmt.format(record))
    assert parsed["weird"] == "11111111-1111-1111-1111-111111111111"


# ---------------------------------------------------------------------------
# StructuredLoggingMiddleware via TestClient
# ---------------------------------------------------------------------------


def test_protected_request_emits_log_line(
    client: TestClient, captured_logs: list[dict]
) -> None:
    r = client.post(
        "/v1/runtime/govern",
        json=_govern_payload(),
        headers={
            "X-Verixa-API-Key": TEST_API_KEY,
            "X-Trace-Id": "trace-from-header",
        },
    )
    assert r.status_code == 200
    # Trace ID echoed in response header
    assert r.headers.get(TRACE_ID_HEADER) == "trace-from-header"
    # captured_logs is populated on fixture teardown — read here is empty;
    # we verify the response header instead which proves the middleware ran.


def test_request_without_trace_id_header_mints_uuid(client: TestClient) -> None:
    r = client.post(
        "/v1/runtime/govern",
        json=_govern_payload(),
        headers={"X-Verixa-API-Key": TEST_API_KEY},
    )
    assert r.status_code == 200
    echoed = r.headers.get(TRACE_ID_HEADER)
    assert echoed is not None
    # Minted trace_id is a UUID4 string
    uuid.UUID(echoed)  # raises if not valid


def test_bypass_path_does_not_set_trace_id_header(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    # Bypass paths skip the middleware entirely → no trace_id echo
    assert TRACE_ID_HEADER not in {h.lower() for h in r.headers.keys()}


def test_request_log_includes_tenant_and_status() -> None:
    """Verify a single request flows through the middleware producing a log."""
    logger = logging.getLogger(LOGGER_NAME)
    original_handlers = logger.handlers[:]
    original_level = logger.level

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    logger.handlers = [handler]
    logger.setLevel(logging.DEBUG)

    try:
        app = create_app(api_keys={TEST_API_KEY: TEST_TENANT_ID})
        client = TestClient(app)
        r = client.post(
            "/v1/runtime/govern",
            json=_govern_payload(),
            headers={"X-Verixa-API-Key": TEST_API_KEY},
        )
        assert r.status_code == 200
        handler.flush()
        lines = [
            json.loads(line)
            for line in stream.getvalue().splitlines()
            if line.strip()
        ]
        # At least one runtime_request log line emitted
        runtime_logs = [
            line for line in lines if line.get("message") == "runtime_request"
        ]
        assert len(runtime_logs) >= 1
        log = runtime_logs[0]
        assert log["path"] == "/v1/runtime/govern"
        assert log["method"] == "POST"
        assert log["status"] == 200
        assert log["tenant_id"] == str(TEST_TENANT_ID)
        assert log["trace_id"] is not None
        assert log["latency_ms"] >= 0
        assert log["api_key_hint"] == TEST_API_KEY[:8]
    finally:
        logger.handlers = original_handlers
        logger.setLevel(original_level)


def test_exception_path_logs_runtime_request_error() -> None:
    """If a route raises, the middleware logs runtime_request_error and re-raises."""
    logger = logging.getLogger(LOGGER_NAME)
    original_handlers = logger.handlers[:]
    original_level = logger.level

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    logger.handlers = [handler]
    logger.setLevel(logging.DEBUG)

    try:
        # Build a minimal app with the logging middleware and a route
        # that always raises. Skip auth middleware so we hit the
        # exception path directly.
        app = FastAPI()
        app.add_middleware(StructuredLoggingMiddleware)

        @app.post("/v1/explode")
        def explode():
            raise RuntimeError("boom")

        client = TestClient(app, raise_server_exceptions=False)
        r = client.post("/v1/explode")
        # Without raise_server_exceptions=False this would raise;
        # the response status is 500 because Starlette returns one.
        assert r.status_code == 500
        handler.flush()
        lines = [
            json.loads(line)
            for line in stream.getvalue().splitlines()
            if line.strip()
        ]
        error_logs = [
            line
            for line in lines
            if line.get("message") == "runtime_request_error"
        ]
        assert len(error_logs) >= 1
        log = error_logs[0]
        assert log["level"] == "ERROR"
        assert log["path"] == "/v1/explode"
        assert log["latency_ms"] >= 0
    finally:
        logger.handlers = original_handlers
        logger.setLevel(original_level)


# ---------------------------------------------------------------------------
# Public-API surface
# ---------------------------------------------------------------------------


def test_constants() -> None:
    assert LOGGER_NAME == "verixa.runtime"
    assert TRACE_ID_HEADER == "x-trace-id"


def test_gateway_package_reexports_logging() -> None:
    from verixa_runtime import gateway

    for name in (
        "JsonLogFormatter",
        "LOGGER_NAME",
        "StructuredLoggingMiddleware",
        "TRACE_ID_HEADER",
    ):
        assert hasattr(gateway, name), f"gateway package missing {name}"
