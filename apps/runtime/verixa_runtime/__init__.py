"""Verixa Runtime Gateway service.

The Runtime Gateway is the primary intercept point for governed AI actions.
It validates against signed policies, scores risk, routes (allow / deny /
escalate / triad), and emits audit-ledger entries.

CP-6+ will populate this package with FastAPI routes, the Tool Call
Firewall, the Policy Engine client, the Risk Engine, the Decision Router,
the Triad Review Engine, and the Replay Vault snapshotter.
"""

__version__ = "0.1.0"
