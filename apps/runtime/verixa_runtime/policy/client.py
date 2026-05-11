"""OPA HTTP client -- async POST to OPA sidecar's data API.

The Verixa runtime calls OPA's REST data endpoint to evaluate a policy:

    POST {OPA_BASE_URL}/v1/data/{package_path}
    {
      "input": <governrequest payload>
    }

OPA returns:

    {
      "result": {
        "decision": "pass" | "fail" | "abstain",
        "reason": "<string>",
        ... (other fields the policy exposes)
      }
    }

This client wraps the call, normalises the response into a typed
``PolicyDecision`` and raises typed errors for transport failures
vs. malformed-OPA-response failures.

Public API:
  - ``PolicyDecision``    frozen dataclass (decision, reason, raw)
  - ``PolicyClientError`` raised on transport / parse failure
  - ``OpaPolicyClient``   client with ``async evaluate(package, input_doc)``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx


class PolicyDecisionKind(str, Enum):
    """Three-valued policy outcome (matches the Rego policies' decision field)."""

    PASS = "pass"  # noqa: S105
    FAIL = "fail"
    ABSTAIN = "abstain"


class PolicyClientError(RuntimeError):
    """Raised when an OPA call fails or the response is malformed."""


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Typed outcome of a policy evaluation."""

    decision: PolicyDecisionKind
    reason: str
    raw: dict[str, Any] = field(default_factory=dict)


def _package_to_url_path(package: str) -> str:
    """``verixa.fs.transfer_amount_limit`` -> ``verixa/fs/transfer_amount_limit``."""
    if not package or "." not in package:
        raise PolicyClientError(
            f"package must be dotted Rego path, got {package!r}"
        )
    return package.replace(".", "/")


def _parse_opa_response(payload: Any, package: str) -> PolicyDecision:
    """Validate + normalise OPA's response body."""
    if not isinstance(payload, dict):
        raise PolicyClientError(
            f"OPA response is not a JSON object for {package}"
        )
    if "result" not in payload:
        # OPA returns 200 with no `result` when the queried path is undefined
        # (no policy matched). We treat this as ABSTAIN.
        return PolicyDecision(
            decision=PolicyDecisionKind.ABSTAIN,
            reason="opa returned no result (path undefined)",
            raw=payload,
        )
    result = payload["result"]
    if not isinstance(result, dict):
        raise PolicyClientError(
            f"OPA response.result is not an object for {package}: "
            f"got {type(result).__name__}"
        )
    raw_decision = result.get("decision")
    if raw_decision is None:
        raise PolicyClientError(
            f"OPA response.result missing 'decision' field for {package}"
        )
    try:
        kind = PolicyDecisionKind(raw_decision)
    except ValueError as e:
        raise PolicyClientError(
            f"OPA returned unknown decision {raw_decision!r} for {package}"
        ) from e
    reason = str(result.get("reason", ""))
    return PolicyDecision(decision=kind, reason=reason, raw=result)


class OpaPolicyClient:
    """Async client for OPA's /v1/data API.

    Phase 0: one client per process; Phase 1 will add a connection pool.
    """

    def __init__(
        self, base_url: str, *, timeout_seconds: float = 5.0
    ) -> None:
        if not base_url:
            raise ValueError("base_url must be a non-empty string")
        # Strip trailing slashes so URL composition is consistent.
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    @property
    def base_url(self) -> str:
        return self._base_url

    async def evaluate(
        self, package: str, input_doc: dict[str, Any]
    ) -> PolicyDecision:
        """Evaluate ``package`` against ``input_doc`` via OPA's data API.

        Raises ``PolicyClientError`` on transport failure or malformed
        response. Never returns ``None`` -- always a typed decision.
        """
        url_path = _package_to_url_path(package)
        url = f"{self._base_url}/v1/data/{url_path}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(url, json={"input": input_doc})
        except httpx.HTTPError as e:
            raise PolicyClientError(
                f"OPA transport error for {package}: {type(e).__name__}: {e}"
            ) from e

        if response.status_code != 200:
            raise PolicyClientError(
                f"OPA returned HTTP {response.status_code} for {package}: "
                f"{response.text[:200]}"
            )
        try:
            body = response.json()
        except ValueError as e:
            raise PolicyClientError(
                f"OPA returned non-JSON body for {package}: {e}"
            ) from e
        return _parse_opa_response(body, package)
