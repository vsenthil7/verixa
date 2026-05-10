"""Verixa Policy Engine -- OPA + Rego.

Verixa policies live as ``.rego`` files under ``policies/<pack>/`` with:

  - ``.manifest`` (OPA bundle manifest -- revision, roots, metadata)
  - one ``.rego`` per policy (declares ``decision`` + ``reason``)
  - ``fixtures/<policy>_fixtures.json`` (pass/fail/abstain test cases)

CP-8 sub-CPs:
  CP-8.1 -- bundle structure + 2 core policies (this commit)
  CP-8.2 -- financial-services pack
  CP-8.3 -- Python OPA HTTP client (calls OPA sidecar)
  CP-8.4 -- bundle signing + signed-bundle verification
  CP-8.5 -- Redis 5s decision cache wrapper

This module exposes a structural loader that callers (CP-12 deployment,
CI bundle-test runner) use to discover and validate the on-disk layout
without launching OPA.
"""

from verixa_runtime.policy.bundle import (  # noqa: F401
    PolicyBundle,
    PolicyBundleError,
    PolicyEntry,
    PolicyFixture,
    PolicyTestExpected,
    discover_bundles,
    load_bundle,
    load_fixtures,
)

__all__ = [
    "PolicyBundle",
    "PolicyBundleError",
    "PolicyEntry",
    "PolicyFixture",
    "PolicyTestExpected",
    "discover_bundles",
    "load_bundle",
    "load_fixtures",
]
