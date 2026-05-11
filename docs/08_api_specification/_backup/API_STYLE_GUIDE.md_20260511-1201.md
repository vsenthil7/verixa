# Verixa API Style Guide

Conventions every Verixa REST endpoint follows. Aligned with **Google API Design Guide** + **Microsoft REST API Guidelines** + **JSON:API** where they agree; deviations are documented inline with rationale.

This is a working document for Phase 0 endpoints (`/v1/control/*`). Phase 1 additions must conform to this guide; deviations require a new ADR.

---

## 1. URL design

- **Versioning in the path:** `/v1/<resource>`. Version is bumped only on **breaking** changes; additive changes do not bump.
- **Resources are nouns, plural:** `/v1/control/workflows`, not `/v1/control/getWorkflows`.
- **Hierarchy is shallow:** at most 2 levels deep (`/v1/control/dossier/{id}`). Deeper nesting goes via query parameters.
- **No verbs in URLs** for CRUD. Use HTTP method instead.
- **Verbs allowed for actions** that are not CRUD-shaped: `/v1/control/replay`, `/v1/control/dossier` (generate). These are documented exceptions because replay and dossier-generate are *operations*, not resources.
- **Lowercase, hyphen-separated** path segments. No `camelCase` or `snake_case` in URLs.

## 2. HTTP methods

| Method | Use |
|---|---|
| `GET` | Retrieve a resource or collection. Idempotent. No request body. |
| `POST` | Create a resource OR invoke an action. Not idempotent in general. |
| `PUT` | Replace a resource entirely. Idempotent. *(Phase 1+)* |
| `PATCH` | Partial update via JSON Merge Patch (RFC 7396). Idempotent. *(Phase 1+)* |
| `DELETE` | Remove a resource. Idempotent. *(Phase 1+; Phase 0 uses cryptographic erasure not deletion)* |

## 3. Request/response format

- **All bodies are JSON.** `Content-Type: application/json`. UTF-8 only.
- **All field names are `snake_case`.** Verixa is Python-first; aligning wire format with the runtime reduces translation bugs.
- **Timestamps are RFC 3339 / ISO 8601 in UTC with `Z` suffix.** Example: `"2026-05-10T09:15:00Z"`. Never local-time. Never numeric Unix epochs in user-facing fields.
- **IDs are UUIDv4** lowercase, with hyphens. Never sequential integers.
- **Booleans are `true` / `false`.** Never `0`/`1` or `"yes"`/`"no"`.
- **Nullable fields are explicit.** The schema declares which fields can be `null`; absence ≠ null.

## 4. Pagination

- Collection endpoints accept `limit` and `cursor` query params. Cursor is opaque (server-generated; clients don't parse it).
- Response shape:
  ```json
  { "items": [...], "next_cursor": "abc123" | null, "total": 42 }
  ```
- **`total` is optional** when an exact count is expensive; clients must not rely on it for non-zero behaviour.
- Default `limit` = 50, max = 500. Larger requests get 400.

## 5. Error responses

- **HTTP status code carries the category** (4xx client error, 5xx server error).
- **Error body** is always:
  ```json
  {
    "error": {
      "code": "policy_violation",
      "message": "Action exceeds workflow transfer limit",
      "details": { "limit": 10000, "attempted": 95000 }
    }
  }
  ```
- `code` is a snake_case enum; clients pattern-match on `code`, never on `message`.
- `message` is human-readable; safe to display.
- `details` is structured; fields depend on `code` and are documented per endpoint.

### Standard codes

| Code | HTTP | Meaning |
|---|---|---|
| `validation_error` | 422 | Pydantic / schema validation failed |
| `bad_request` | 400 | Well-formed but semantically rejected |
| `unauthorized` | 401 | Missing or invalid credentials *(Phase 1+)* |
| `forbidden` | 403 | Authenticated but lacks permission |
| `not_found` | 404 | Resource does not exist |
| `conflict` | 409 | State conflict (e.g. duplicate registration) |
| `policy_violation` | 422 | Action denied by policy engine |
| `firewall_reject` | 403 | Tool firewall rejected the call |
| `rate_limited` | 429 | Throttled *(Phase 1+)* |
| `internal_error` | 500 | Unexpected server error |

## 6. Authentication

- **Phase 0**: no auth on the Control Plane API (single-tenant demo container). Documented honestly.
- **Phase 1+**: bearer tokens via `Authorization: Bearer <token>` header. Token format TBD (likely opaque server-issued, not JWT in the runtime path — see Phase 1 ADR).

## 7. Idempotency

- Action endpoints (`/replay`, `/dossier`) accept an optional `Idempotency-Key` header. Repeated requests with the same key return the same response.
- Phase 0 stores keys in-memory; Phase 1 persists them with a 24-hour TTL.

## 8. Compatibility & deprecation

- **Additive changes don't bump the version.** Adding optional fields, new endpoints, new enum values: minor.
- **Removing a field or changing its meaning** is breaking → new `/v2/`.
- **Deprecated fields** are kept in the response with a `deprecation` warning in the OpenAPI spec for at least one minor release.

## 9. OpenAPI

- The Control Plane API auto-generates an OpenAPI 3.1 spec at `/openapi.json` and a Swagger UI at `/docs`.
- The spec is the single source of truth. Anything not in the spec is not part of the API contract.

## 10. Examples

Every endpoint in the OpenAPI spec carries at least one request example + one success response example + one failure response example. Phase 0's `/v1/control/workflows` and `/v1/control/audit` examples are seeded from the demo data so a Swagger UI user can hit "Try it out" with realistic values pre-filled.

---

## Deviations from convention (recorded)

- **Replay and dossier are verb-shaped endpoints** (`/v1/control/replay`, `/v1/control/dossier`). Rationale: they are operations against the *audit history*, not against any one resource. Modelling them as `POST /v1/control/audit/{id}/replay` was considered but rejected because the audit entry is not the replay's input — the audit *id* is, plus optional decryption-key context that's not part of the audit resource.
- **`/v1/control/audit` accepts query params for time-window filtering rather than separate range resources.** Standard REST pattern; flagged because some style guides argue for `/v1/control/audit/range/2026-Q1`. Verixa chose query params for flexibility.

## Related

- ADR-0005 (Mermaid for diagrams) — separate doc-tooling decision
- BR-08 (operator surface)
- All `apps/control-plane-api/verixa_control_plane/routes.py` endpoints conform to this guide; enforced by 16 Pydantic envelope tests in `apps/control-plane-api/tests/test_envelopes.py`
