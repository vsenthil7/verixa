"""Verixa Risk Engine + Decision Router.

Replaces the Phase-0 stub ``decide_phase0`` from CP-6.2 with a real
policy-aware decision router.

Pipeline (a single governed request flows through this in order):

    1. Firewall allow-list   (from CP-7.1) -> verdict
    2. Firewall arg-bounds   (from CP-7.2) -> verdict
    3. Policy evaluations    (from CP-8 OPA pipeline) -> decisions[]
    4. Risk score            (this module) -> scalar 0..1
    5. Decision router       (this module) -> final allow/deny/escalate

The router is **pure** -- it takes already-computed firewall verdicts
and policy decisions as inputs and returns a typed ``GovernResponse``.
The actual I/O (firewall registry lookup, OPA call) lives in the
gateway layer (CP-9.2). Keeping the router pure makes it trivial to
test the decision logic without mocking HTTP, Redis, or DB.

Decision rules (evaluated in order; first match wins):

  R1. ANY firewall deny  -> DENY  (reason from firewall)
  R2. ANY policy fail    -> DENY  (reason from first failing policy;
                                   risk classified by which policies
                                   failed)
  R3. ANY policy abstain -> ESCALATE (human review needed; OPA
                                       returned no opinion)
  R4. ALL policies pass  -> ALLOW

Risk score (scalar 0..1; informational, not used to flip decisions in
Phase 0 -- CP-15 wires it into rate-limit weighting):

  - Each fail contributes 0.30
  - Each abstain contributes 0.10
  - Firewall deny adds 0.50 (terminal)
  - Capped at 1.0

Risk classification (matches docs/05_api 'risk_classification' field):

  >= 0.80 -> CRITICAL
  >= 0.50 -> HIGH
  >= 0.20 -> MEDIUM
  else    -> LOW

Public API:
  - ``RouterInputs``      frozen dataclass of inputs
  - ``compute_risk``      pure scoring function
  - ``classify_risk``     pure classification function
  - ``route_decision``    the orchestrator -- pure
"""

from verixa_runtime.risk.router import (  # noqa: F401
    RouterInputs,
    classify_risk,
    compute_risk,
    route_decision,
)

__all__ = [
    "RouterInputs",
    "classify_risk",
    "compute_risk",
    "route_decision",
]
