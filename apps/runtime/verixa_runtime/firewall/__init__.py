"""Verixa Tool Call Firewall.

Sits between the gateway envelope and the policy engine. Every action
of type ``tool_call`` passes through two sequential checks:

  1. Allow-list: is the tool registered, active, and permitted for the
     caller's workflow?  (CP-7.1, this commit)
  2. Argument bounds: do the supplied arguments satisfy the tool's
     declared bounds (numeric ranges, string lengths/patterns, array
     sizes)?  (CP-7.2)

A failing firewall produces a ``FirewallVerdict(decision='deny', ...)``
that the gateway maps to a ``GovernResponse`` with ``decision=deny``,
``reason='firewall_denied'``, and the firewall's specific message.

The firewall is pure: no DB, no network. The caller (CP-12 wires this)
loads the tool registry from ``verixa_registry.tools`` and passes it in.

Public API (CP-7.1):
  - `FirewallDecision`           Enum allow / deny
  - `FirewallVerdict`            frozen dataclass (decision, reason, code)
  - `ToolRegistryEntry`          frozen dataclass mirroring verixa_registry.tools
  - `evaluate_allowlist`         pure function
"""

from verixa_runtime.firewall.allowlist import (  # noqa: F401
    FirewallDecision,
    FirewallVerdict,
    ToolRegistryEntry,
    evaluate_allowlist,
)

__all__ = [
    "FirewallDecision",
    "FirewallVerdict",
    "ToolRegistryEntry",
    "evaluate_allowlist",
]
