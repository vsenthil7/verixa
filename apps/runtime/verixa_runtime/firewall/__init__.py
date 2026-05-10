"""Verixa Tool Call Firewall.

Sits between the gateway envelope and the policy engine. Every action
of type ``tool_call`` passes through two sequential checks:

  1. Allow-list: is the tool registered, active, and permitted for the
     caller's workflow?  (CP-7.1)
  2. Argument bounds: do the supplied arguments satisfy the tool's
     declared bounds (numeric ranges, string lengths/patterns, array
     sizes)?  (CP-7.2, this commit)

A failing firewall produces a ``FirewallVerdict(decision='deny', ...)``
that the gateway maps to a ``GovernResponse`` with ``decision=deny``,
``reason='firewall_denied'``, and the firewall's specific message.

The firewall is pure: no DB, no network. The caller (CP-12 wires this)
loads the tool registry from ``verixa_registry.tools`` and passes it in.
"""

from verixa_runtime.firewall.allowlist import (  # noqa: F401
    FirewallDecision,
    FirewallVerdict,
    ToolRegistryEntry,
    evaluate_allowlist,
)
from verixa_runtime.firewall.arg_bounds import (  # noqa: F401
    CODE_ARG_ARRAY_SIZE,
    CODE_ARG_ENUM,
    CODE_ARG_FORMAT,
    CODE_ARG_LENGTH,
    CODE_ARG_MISSING,
    CODE_ARG_MULTIPLE_OF,
    CODE_ARG_PATTERN,
    CODE_ARG_RANGE,
    CODE_ARG_TYPE,
    CODE_ARG_UNKNOWN,
    evaluate_argument_bounds,
)

__all__ = [
    "CODE_ARG_ARRAY_SIZE",
    "CODE_ARG_ENUM",
    "CODE_ARG_FORMAT",
    "CODE_ARG_LENGTH",
    "CODE_ARG_MISSING",
    "CODE_ARG_MULTIPLE_OF",
    "CODE_ARG_PATTERN",
    "CODE_ARG_RANGE",
    "CODE_ARG_TYPE",
    "CODE_ARG_UNKNOWN",
    "FirewallDecision",
    "FirewallVerdict",
    "ToolRegistryEntry",
    "evaluate_allowlist",
    "evaluate_argument_bounds",
]
