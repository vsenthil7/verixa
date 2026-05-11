"""CP-30 negative test 5/5: path-traversal payloads.

Anchored to BR-02 (input validation), BR-07 (audit-trail completeness),
NEGATIVE_TEST_PLAN section 6 (path traversal / injection payloads).

Path-traversal payloads target string fields that downstream code
might pass to a filesystem or URL builder. In Verixa Phase 0 the
fields most at risk are:
  - doc_id in RetrievedDocument
  - tool_name in GovernAction
  - role and spiffe_id in AgentIdentity

The envelope schema does NOT itself touch the filesystem -- it's a
pure data layer. The defence is "preserve verbatim in the audit log,
let downstream consumers (storage, dossier filename, MinIO key)
apply their own escaping". These tests document that the envelope
layer DOES preserve verbatim, so downstream consumers KNOW they must
escape; AND that fields with strict schemas (hash, prompt_hash,
UUID) cannot be smuggled with path-traversal sequences; AND that
very-long traversal payloads are length-capped at the validator.

Adversarial framing: an attacker controls one string field
(doc_id or tool_name) and tries to escape into "wrong directory"
when the dossier generator writes a per-bundle file or when MinIO
keys are constructed.

CP-30 RED at 3b884ad: doc_id has a length cap; 100-element
traversal chain is rejected. This GREEN commit moves the long-chain
case to its own rejection-asserting test.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError
from verixa_runtime.gateway.envelopes import (
    AgentIdentity,
    GovernAction,
    GovernContext,
    RetrievedDocument,
)

_WF_ID = uuid.UUID("99999999-9999-9999-9999-999999999999")


# ---------------------------------------------------------------------------
# Path-traversal payloads preserved verbatim in free-text fields
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        "../../../etc/passwd",
        "..\\..\\..\\Windows\\System32",
        "%2e%2e%2fetc%2fpasswd",  # URL-encoded
        "/etc/passwd",
        "C:\\Windows\\System32\\config",
        "doc.txt\x00../../../etc/passwd",  # null-byte truncation
    ],
)
def test_path_traversal_in_doc_id_preserved_verbatim(payload: str) -> None:
    """doc_id is a free-form string. The envelope MUST preserve the
    bytes exactly so a forensic reviewer sees the attempted
    traversal. Downstream consumers (MinIO key, dossier filename)
    are responsible for escaping; that boundary is asserted in
    storage-layer tests not here."""
    rd = RetrievedDocument(doc_id=payload, hash="a" * 64)
    assert rd.doc_id == payload


def test_extremely_long_traversal_chain_in_doc_id_rejected() -> None:
    """A 400+ char traversal chain in doc_id is rejected by the
    doc_id length cap. Defence against size-bomb-via-traversal-chain
    attack. Discovered as CP-30 RED at 3b884ad."""
    payload = "..\\" * 100  # 400 chars
    with pytest.raises(ValidationError, match="too_long|too long"):
        RetrievedDocument(doc_id=payload, hash="a" * 64)


@pytest.mark.parametrize(
    "payload",
    [
        "../malicious_tool",
        "..\\nope",
        "/bin/sh",
        "tool.exe\x00../etc/passwd",
    ],
)
def test_path_traversal_in_tool_name_preserved_verbatim(payload: str) -> None:
    """tool_name in GovernAction. The firewall allowlist applies a
    set-membership check (not a path operation) so traversal payloads
    that aren't in the allowlist are denied at the firewall layer.
    Here we assert the envelope preserves verbatim so the firewall
    sees the real bytes."""
    act = GovernAction.model_validate(
        {"type": "tool_call", "tool_name": payload}
    )
    assert act.tool_name == payload


@pytest.mark.parametrize(
    "payload",
    [
        "../etc/passwd",
        "..\\..\\..",
        "/etc/shadow",
        "C:\\Users\\Administrator",
    ],
)
def test_path_traversal_in_role_preserved_verbatim(payload: str) -> None:
    """role is a free-form string. Audit log must capture verbatim
    so a reviewer sees an attempted role-name traversal."""
    agent = AgentIdentity(
        spiffe_id="spiffe://x", role=payload, workflow_id=_WF_ID
    )
    assert agent.role == payload


# ---------------------------------------------------------------------------
# Fixed-format fields reject traversal payloads (length/charset invariants)
# ---------------------------------------------------------------------------


def test_path_traversal_in_hash_rejected_by_length() -> None:
    """A path-traversal payload in the hash field is rejected because
    the regex requires exactly 64 hex chars. Traversal payloads have
    slashes / dots / etc that aren't hex."""
    with pytest.raises(ValidationError):
        RetrievedDocument(doc_id="x", hash="../../../etc/passwd")


def test_path_traversal_in_prompt_hash_rejected_by_format() -> None:
    """prompt_hash is hex-only. Slashes break the regex."""
    with pytest.raises(ValidationError):
        GovernContext(
            prompt_hash="/etc/passwd" + "a" * 53, model_version="m"
        )


def test_path_traversal_in_workflow_id_rejected_as_invalid_uuid() -> None:
    """workflow_id is UUID. Traversal payload is not a valid UUID."""
    with pytest.raises(ValidationError):
        AgentIdentity.model_validate(
            {
                "spiffe_id": "spiffe://x",
                "role": "r",
                "workflow_id": "../../../etc/passwd",
            }
        )


# ---------------------------------------------------------------------------
# Tool argument bounds: path-traversal in tool args
# ---------------------------------------------------------------------------


def test_path_traversal_in_tool_args_preserved() -> None:
    """tool args are stored as dict[str, Any]. Path-traversal
    payloads in args go to the firewall arg-bounds layer where the
    per-tool schema decides. Envelope preserves verbatim."""
    args = {"file_path": "../../../etc/passwd"}
    act = GovernAction.model_validate(
        {"type": "tool_call", "tool_name": "read_file", "arguments": args}
    )
    assert act.arguments["file_path"] == "../../../etc/passwd"


def test_path_traversal_in_deeply_nested_tool_args_preserved() -> None:
    """Path traversal in a nested args structure preserved verbatim."""
    args = {
        "config": {
            "nested": {
                "deeper": {
                    "file_path": "..\\..\\Windows\\System32\\config\\SAM"
                }
            }
        }
    }
    act = GovernAction.model_validate(
        {"type": "tool_call", "tool_name": "x", "arguments": args}
    )
    config = act.arguments["config"]
    assert isinstance(config, dict)
    nested = config["nested"]
    assert isinstance(nested, dict)
    deeper = nested["deeper"]
    assert isinstance(deeper, dict)
    assert deeper["file_path"] == "..\\..\\Windows\\System32\\config\\SAM"
