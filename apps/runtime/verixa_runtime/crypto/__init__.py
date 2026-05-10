"""Verixa cryptographic primitives.

Three primitives ship in this package, each in its own module:

- `ed25519`      — Ed25519 sign/verify (audit-ledger signatures)
- `hash_chain`   — SHA-256 hash chain (audit-ledger integrity)
- `aes_gcm`      — AES-256-GCM encrypt/decrypt (replay-vault snapshots)

Plus a key-bootstrap utility for dev-mode tenant key-pair generation
(production uses HashiCorp Vault transit / customer-supplied KMS).

Design rules (carried from docs/06_data_model + docs/07_threat_model):

1. **Determinism where possible:** signature/hash functions take bytes,
   return bytes; no implicit time, no implicit RNG, no implicit globals
   except where a `secrets`-grade RNG is genuinely required (key-gen,
   nonces).
2. **Type discipline:** primitives accept and return `bytes`; callers
   are responsible for encoding (PEM for keys, base64 for transport,
   hex for human display).
3. **No silent failures:** every verify path raises a typed exception
   on failure; never returns a bool. Callers `try / except` at the
   policy boundary.
4. **No defensive code that can't be tested:** every branch must be
   reachable from the test suite (see Auditex BLD-019 file-level
   invariant pattern carried into compliance_language.ts).
"""

from verixa_runtime.crypto.ed25519 import (  # noqa: F401
    Ed25519KeyPair,
    Ed25519SignatureError,
    generate_keypair,
    sign,
    verify,
)

__all__ = [
    "Ed25519KeyPair",
    "Ed25519SignatureError",
    "generate_keypair",
    "sign",
    "verify",
]
