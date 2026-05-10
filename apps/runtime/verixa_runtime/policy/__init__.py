"""Verixa Policy Engine -- OPA + Rego.

Verixa policies live as ``.rego`` files under ``policies/<pack>/`` with:

  - ``.manifest`` (OPA bundle manifest -- revision, roots, metadata)
  - ``.signatures.json`` (Ed25519-signed manifest of file SHA-256s)
  - one ``.rego`` per policy (declares ``decision`` + ``reason``)
  - ``fixtures/<policy>_fixtures.json`` (pass/fail/abstain test cases)

CP-8 sub-CPs:
  CP-8.1 -- bundle structure + 2 core policies
  CP-8.2 -- financial-services pack
  CP-8.3 -- Python OPA HTTP client
  CP-8.4 -- bundle signing + signed-bundle verification
  CP-8.5 -- Redis 5s decision cache wrapper (this commit)
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
from verixa_runtime.policy.cache import (  # noqa: F401
    CACHE_KEY_PREFIX,
    CACHE_TTL_SECONDS,
    CachedPolicyClient,
    CacheStats,
    RedisLike,
)
from verixa_runtime.policy.client import (  # noqa: F401
    OpaPolicyClient,
    PolicyClientError,
    PolicyDecision,
    PolicyDecisionKind,
)
from verixa_runtime.policy.signing import (  # noqa: F401
    SIGNATURES_FILENAME,
    SIGNATURES_VERSION,
    BundleSignatures,
    BundleSignaturesError,
    compute_bundle_file_hashes,
    sign_bundle,
    verify_bundle_signatures,
)

__all__ = [
    "BundleSignatures",
    "BundleSignaturesError",
    "CACHE_KEY_PREFIX",
    "CACHE_TTL_SECONDS",
    "CacheStats",
    "CachedPolicyClient",
    "OpaPolicyClient",
    "PolicyBundle",
    "PolicyBundleError",
    "PolicyClientError",
    "PolicyDecision",
    "PolicyDecisionKind",
    "PolicyEntry",
    "PolicyFixture",
    "PolicyTestExpected",
    "RedisLike",
    "SIGNATURES_FILENAME",
    "SIGNATURES_VERSION",
    "compute_bundle_file_hashes",
    "discover_bundles",
    "load_bundle",
    "load_fixtures",
    "sign_bundle",
    "verify_bundle_signatures",
]
