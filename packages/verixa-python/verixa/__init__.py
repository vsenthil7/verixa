"""Verixa shared Python library (cross-cutting types, constants, helpers).

This package contains code shared between the Runtime Gateway and the
Control Plane API, plus the customer-facing SDK for talking to a
deployed Verixa control plane.

Public SDK surface (re-exported from sdk.py for ergonomic imports):

    from verixa import VerixaClient, VerixaError, VerixaHttpError
"""

__version__ = "0.1.0"
__author__ = "v_sen"
__license__ = "MIT"

from verixa.sdk import (
    AgentsClient,
    AuditClient,
    BundlesClient,
    DossierClient,
    ReplayClient,
    ToolsClient,
    VerixaClient,
    VerixaConnectionError,
    VerixaError,
    VerixaHttpError,
    WebhooksClient,
    WorkflowsClient,
)

__all__ = [
    "AgentsClient",
    "AuditClient",
    "BundlesClient",
    "DossierClient",
    "ReplayClient",
    "ToolsClient",
    "VerixaClient",
    "VerixaConnectionError",
    "VerixaError",
    "VerixaHttpError",
    "WebhooksClient",
    "WorkflowsClient",
]
