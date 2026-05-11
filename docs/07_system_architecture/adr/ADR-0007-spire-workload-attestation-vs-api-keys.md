# ADR-0007 — SPIRE workload attestation vs API-key tenant auth

- **Status:** Proposed (Phase 1 placeholder)
- **Date:** 2026-05-11
- **Phase:** 1 (production rollout)
- **Decision owner:** TBD at Phase 1 kickoff
- **Affects:** Agent → Verixa runtime authentication, multi-tenant identity, mTLS roll-out

## Context

Phase 0 has **no auth** on the Control Plane API (single-tenant demo container; documented honestly in API_STYLE_GUIDE §6). Phase 1 must add authentication for two distinct surfaces:

1. **Agent → Runtime gateway.** Customer-owned agents (loan officers, healthcare assistants, etc.) call `/v1/runtime/govern` from their own infrastructure. The runtime must know which tenant + which agent + which workflow before invoking the firewall and policy engine.

2. **Operator → Control Plane API.** Tenant operators view audit logs, replay decisions, generate dossiers. This is a human-or-service-account access pattern.

The agent→runtime path is the harder problem because:

- Agents run in customer infrastructure; Verixa cannot mandate a specific deployment model.
- Per-call latency matters (governance is on the critical path of agent decisions).
- Spoofing one agent as another would let an attacker bypass per-agent policies.

The envelope already carries `agent_identity: { spiffe_id, role, workflow_id }` (CP-6) — the field name suggests the design intent.

## Decision (preliminary lean)

**Two-tier auth:**

1. **Agent → Runtime: SPIFFE/SPIRE workload attestation** with mTLS. Agents present an X.509 SVID issued by a SPIRE server federated with the customer's existing workload-identity infrastructure. The `spiffe_id` field in the envelope is verified against the SVID at the TLS layer.

2. **Operator → Control Plane: API keys** issued per tenant + per operator role. Simple bearer-token auth via `Authorization: Bearer <key>` header. Keys are tenant-scoped; operators cannot cross tenants without explicit super-admin grants.

Final decision deferred to Phase 1 kickoff after Phase 1 design-partner customers tell us their existing identity infrastructure.

## Consequences

### Positive

- **SPIFFE is the right primitive** for workload-to-workload auth. CNCF graduated standard. Federates with Kubernetes service accounts, AWS IAM roles, Azure managed identities — every customer's existing identity infrastructure.
- **mTLS gives transport-layer confidentiality** without app-layer key management.
- **Per-call latency stays low.** SVID verification is cached per-connection (mTLS handshake amortises).
- **API keys for operators are simple to issue, rotate, revoke.** Operators don't need workload identity; humans don't have SPIFFE IDs.

### Negative

- **SPIRE is operationally heavy.** Customers without existing SPIRE infrastructure must run a SPIRE server, configure attestation plugins, and integrate with their workload deployment. High onboarding friction.
- **mTLS adds latency** versus token auth (~5-10ms handshake; amortised but real). Phase 1 must measure.
- **Two auth systems is more code to maintain** than one. Bug surface area is larger.
- **API keys leak.** Token-based auth is vulnerable to log exposure, accidental commits, shoulder-surfing. Phase 1 must add token-scope-down-by-default, rotation enforcement, and audit-log every key use.

### Mitigations

- Provide a **simpler "trust-on-first-use" mode** for customers without SPIRE: agents register with an enrolment token and receive a long-lived API key tied to their `spiffe_id`. Workload-attestation comes as an opt-in upgrade.
- Document the SPIRE setup with a working `docker-compose` example. Hide the operational complexity behind a Verixa-supplied SPIRE server image for design-partner customers.
- For operator API keys: enforce 90-day rotation, audit-log every use, support scoped tokens (read-only vs read-write).

## Alternatives considered

1. **JWT-only auth** (no mTLS). Rejected for agent→runtime because JWTs in headers leak in logs and proxies; mTLS scopes confidentiality to the transport layer where leaks are harder.
2. **OAuth 2.0 / OIDC for everything.** Rejected because agents are workloads, not users; the OAuth flow doesn't fit. Operator access via OIDC is a Phase 2 extension.
3. **mTLS without SPIFFE.** Rejected because cert provisioning becomes Verixa's problem; SPIFFE is the explicit "delegate identity to your existing infrastructure" answer.
4. **API keys for everything.** Rejected for agent→runtime because per-agent key rotation at scale (thousands of agents per tenant) is operationally infeasible.
5. **OPA-as-auth.** Rejected. OPA evaluates policy; SPIRE attests identity. Using OPA for both conflates two responsibilities and makes audit trails confusing.

## Verification

- Phase 1 must demonstrate one design-partner customer using SPIRE federated with their existing infrastructure (typical: Kubernetes service accounts or AWS IAM).
- mTLS handshake p95 latency must be under 20ms across customer ↔ Verixa boundary.
- Operator API-key rotation must complete with zero downtime.
- Audit log must record every successful and failed auth event with sufficient detail for forensics.

## Related

- ADR-0008 (Vault vs KMS for signing-key custody) — closely related; the SPIRE server's signing keys themselves live in whatever key-custody system ADR-0008 selects
- BR-01 (auditable governance) — auth events are audit events
- BR-06 (multi-tenant isolation) — auth is the foundation of tenant isolation
- `docs/10_security_architecture/SECURITY_ARCHITECTURE.md` — broader auth context
- `apps/runtime/verixa_runtime/gateway/envelopes.py::AgentIdentity` — already carries `spiffe_id` field anticipating this decision
