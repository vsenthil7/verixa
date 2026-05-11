"""CP-45 -- OPA bundle distribution server.

Closes the Phase-1 bundle-distribution gap left open by CP-43 (signing CLI
already landed; distribution server pending).

OPA's standard pull model expects a bundle service to expose:

    GET /bundles/<name>            -> 200 with tar.gz body + ETag header
    GET /bundles/<name>            -> 304 if If-None-Match matches current ETag

Reference: https://www.openpolicyagent.org/docs/latest/management-bundles/

Verixa hardens this with three additional guarantees beyond the OPA spec:

  1. **Refuse to serve unsigned bundles.** Every bundle MUST have a valid
     ``.signatures.json`` (produced by CP-43 policy_sign CLI) BEFORE the
     server will package and emit it. An unsigned bundle in the source
     tree is a deployment error, not a serve-degraded-mode condition.

  2. **Tar-gz produced deterministically.** Same bundle contents always
     produce same tar.gz bytes, which means the ETag is content-addressed.
     If an operator publishes the same bundle twice the ETag is stable,
     so OPA caches don't churn unnecessarily.

  3. **Bundle name validated against a strict allow-list pattern.** No
     path traversal, no special characters, no Unicode tricks. Bundle
     names that came from URL paths NEVER reach the filesystem without
     this check (defence-in-depth even when the routing layer pins the
     path).

Public API:

  - ``BundleServerError``       -- raised on any serve failure
  - ``BundleNotFound``          -- the requested name doesn't resolve
  - ``BundleUnsigned``          -- bundle directory has no .signatures.json
  - ``BundleNameInvalid``       -- name fails the allow-list pattern
  - ``BundleArtifact``          -- frozen result of packaging
  - ``BundleServer``            -- the main class; holds the policies root
  - ``valid_bundle_name``       -- pure-function validator (also used by routes)

Phase-2 carry-forward: signed-bundle freshness windows (revoke an old
signing key after compromise) and per-customer key pinning live in
ADR-0008. This module only validates the *current* signature; key-rotation
infra lands when ADR-0011 is approved.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import re
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from verixa_runtime.policy.signing import (
    SIGNATURES_FILENAME,
    BundleSignatures,
    BundleSignaturesError,
    verify_bundle_signatures,
)

# Bundle-name allow-list: lowercase letters, digits, hyphen, underscore.
# Length 1-64 to keep URL paths sane. NO dots (defence-in-depth against
# ../traversal even when the routing layer pins the path), NO slashes,
# NO unicode.
_BUNDLE_NAME_RE: Final = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

# Use a fixed mtime when building the tarball so the same source produces
# the same bytes -- enables content-addressable ETags. 2020-01-01 is
# arbitrary but well-defined.
_DETERMINISTIC_MTIME: Final[int] = 1577836800  # 2020-01-01 00:00 UTC


class BundleServerError(RuntimeError):
    """Base class for bundle-server failures."""


class BundleNotFound(BundleServerError):
    """The requested bundle name does not exist under the policies root."""


class BundleUnsigned(BundleServerError):
    """Bundle directory has no valid .signatures.json -- refuse to serve."""


class BundleNameInvalid(BundleServerError):
    """Bundle name does not match the allow-list pattern."""


@dataclass(frozen=True, slots=True)
class BundleArtifact:
    """A packaged bundle, ready to send over HTTP.

    Attributes:
      name:         the bundle name (already validated)
      tarball:      gzip-compressed tar bytes (the HTTP body)
      etag:         strong ETag for HTTP caching ("<sha256-hex>")
      signatures:   parsed .signatures.json for downstream logging
      generated_at: monotonic timestamp for SLI logging (NOT for caching)
    """

    name: str
    tarball: bytes
    etag: str
    signatures: BundleSignatures
    generated_at: float


def valid_bundle_name(name: str) -> bool:
    """Return True iff name passes the allow-list pattern.

    Pure function: callable from routing layer for early rejection
    before the request even reaches the BundleServer instance.
    """
    if not isinstance(name, str):
        return False
    return bool(_BUNDLE_NAME_RE.match(name))


def _files_to_pack(bundle_dir: Path) -> list[Path]:
    """Return every file the bundle tarball will contain, sorted.

    Includes ``.signatures.json`` (consumers verify the signature on
    receipt). Excludes any other dot-files except ``.manifest`` and
    ``.signatures.json``.
    """
    out: list[Path] = []
    for p in bundle_dir.rglob("*"):
        if p.is_dir():
            continue
        rel = p.relative_to(bundle_dir).as_posix()
        first = rel.split("/", 1)[0]
        if first.startswith(".") and first not in (
            ".manifest",
            SIGNATURES_FILENAME,
        ):
            continue
        out.append(p)
    out.sort(key=lambda p: p.relative_to(bundle_dir).as_posix())
    return out


def _build_tarball(bundle_dir: Path, files: list[Path]) -> bytes:
    """Build a deterministic gzipped-tar of the bundle.

    Determinism guarantees same-source -> same-bytes -> same-ETag.
    Determinism details:
      - Fixed mtime per file (so timestamps don't churn)
      - Fixed uid/gid (0) and uname/gname ("") (so build-host doesn't leak)
      - Fixed file permissions (0o644) (so umask doesn't churn)
      - Sorted file list (so directory-listing order doesn't matter)
      - gzip mtime = 0 (so the gzip header doesn't churn)
    """
    raw = io.BytesIO()
    # Wrap gzip.GzipFile with explicit mtime=0 so the gzip header is
    # deterministic; tarfile.open(mode="w:gz") would embed time.time()
    # into the gzip header and break content-addressing. tarfile is then
    # wrapped around the pre-configured gzip stream in mode "w" (no
    # compression at the tar layer; gzip is doing the compression).
    with gzip.GzipFile(
        fileobj=raw, mode="wb", compresslevel=6, mtime=0
    ) as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for path in files:
                rel_posix = path.relative_to(bundle_dir).as_posix()
                data = path.read_bytes()
                info = tarfile.TarInfo(name=rel_posix)
                info.size = len(data)
                info.mtime = _DETERMINISTIC_MTIME
                info.mode = 0o644
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                info.type = tarfile.REGTYPE
                tar.addfile(info, io.BytesIO(data))
    return raw.getvalue()


def _compute_etag(tarball: bytes) -> str:
    """Strong ETag = SHA-256 hex of the tarball. Quoted per RFC 7232."""
    return f'"{hashlib.sha256(tarball).hexdigest()}"'


class BundleServer:
    """Serves signed policy bundles as gzipped tarballs.

    The server holds a reference to a policies root directory. Each
    ``serve(name)`` call:

      1. Validates the name against the allow-list
      2. Resolves the bundle dir under the policies root
      3. Verifies the bundle's .signatures.json (refuses to serve if absent
         or tampered)
      4. Packages the bundle into a deterministic tar.gz
      5. Computes the ETag from the tarball bytes
      6. Returns a BundleArtifact

    The server is stateless: a fresh BundleArtifact is produced per call.
    Callers (FastAPI routes) handle HTTP-level caching by comparing the
    incoming If-None-Match header to the ETag and returning 304 when they
    match.

    Phase-2 carry: persistent in-memory cache of artifacts keyed by
    bundle-dir mtime, so repeated GETs don't re-tar. Not implemented here
    because tarball generation is sub-millisecond for typical bundles and
    a stale-cache key would need invalidation logic.
    """

    def __init__(self, policies_root: Path) -> None:
        self._policies_root = Path(policies_root).resolve()
        if not self._policies_root.is_dir():
            raise BundleServerError(
                f"policies root is not a directory: {self._policies_root}"
            )

    @property
    def policies_root(self) -> Path:
        """The absolute policies-root path the server was constructed with."""
        return self._policies_root

    def list_bundles(self) -> list[str]:
        """Return the sorted list of bundle names available to serve.

        A directory under the policies root counts as a bundle iff it
        contains both ``.manifest`` and ``.signatures.json``. Bundles
        with names that fail the allow-list are excluded (cannot be
        served via the HTTP API anyway).
        """
        out: list[str] = []
        for child in sorted(self._policies_root.iterdir()):
            if not child.is_dir():
                continue
            if not (child / ".manifest").is_file():
                continue
            if not (child / SIGNATURES_FILENAME).is_file():
                continue
            if not valid_bundle_name(child.name):
                continue
            out.append(child.name)
        return out

    def serve(self, name: str) -> BundleArtifact:
        """Package and return one bundle. Raises on validation failures."""
        if not valid_bundle_name(name):
            raise BundleNameInvalid(
                f"bundle name {name!r} fails allow-list: "
                f"must match [a-z0-9][a-z0-9_-]{{0,63}}"
            )
        # Resolve and bound-check against the policies root (belt + braces:
        # the regex already rejects '..' but a second resolve+check is cheap).
        bundle_dir = (self._policies_root / name).resolve()
        try:
            bundle_dir.relative_to(self._policies_root)
        except ValueError as e:  # pragma: no cover -- defence-in-depth
            raise BundleNameInvalid(
                f"bundle name {name!r} resolves outside policies root"
            ) from e
        if not bundle_dir.is_dir():
            raise BundleNotFound(
                f"bundle {name!r} not found under {self._policies_root}"
            )
        sig_path = bundle_dir / SIGNATURES_FILENAME
        if not sig_path.is_file():
            raise BundleUnsigned(
                f"bundle {name!r} has no {SIGNATURES_FILENAME}; "
                f"sign it with `tools/policy_sign.py sign` before serving"
            )
        try:
            signatures = verify_bundle_signatures(bundle_dir)
        except BundleSignaturesError as e:
            raise BundleUnsigned(
                f"bundle {name!r} signature verification failed: {e}"
            ) from e

        files = _files_to_pack(bundle_dir)
        tarball = _build_tarball(bundle_dir, files)
        etag = _compute_etag(tarball)
        return BundleArtifact(
            name=name,
            tarball=tarball,
            etag=etag,
            signatures=signatures,
            generated_at=time.monotonic(),
        )


__all__ = [
    "BundleArtifact",
    "BundleNameInvalid",
    "BundleNotFound",
    "BundleServer",
    "BundleServerError",
    "BundleUnsigned",
    "valid_bundle_name",
]
