"""Verixa shared Python library (cross-cutting types, constants, helpers).

This package contains code shared between the Runtime Gateway and the
Control Plane API, plus the customer-facing SDK for talking to a
deployed Verixa control plane.

Public SDK surface (re-exported from sdk.py for ergonomic imports):

    from verixa import VerixaClient, VerixaError, VerixaHttpError

Typed response envelopes (re-exported from envelopes.py):

    from verixa import WorkflowRegisterResponse, AuditEntry, ...

The full server-side response envelope set is mirrored as of CP-64.
"""

__version__ = "0.1.0"
__author__ = "v_sen"
__license__ = "MIT"

from verixa.envelopes import (
    AgentRegisterResponse,
    AuditEntry,
    AuditQueryResponse,
    DossierGenerateResponse,
    DossierGetResponse,
    InvalidEnvelopeError,
    ReplayResponse,
    ToolRegisterResponse,
    WebhookDeliveryListResponse,
    WebhookDeliverySummary,
    WebhookSubscriptionListResponse,
    WebhookSubscriptionSummary,
    WorkflowListResponse,
    WorkflowRegisterResponse,
    WorkflowSummary,
)
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
    "AgentRegisterResponse",
    "AgentsClient",
    "AuditClient",
    "AuditEntry",
    "AuditQueryResponse",
    "BundlesClient",
    "DossierClient",
    "DossierGenerateResponse",
    "DossierGetResponse",
    "InvalidEnvelopeError",
    "ReplayClient",
    "ReplayResponse",
    "ToolRegisterResponse",
    "ToolsClient",
    "VerixaClient",
    "VerixaConnectionError",
    "VerixaError",
    "VerixaHttpError",
    "WebhookDeliveryListResponse",
    "WebhookDeliverySummary",
    "WebhookSubscriptionListResponse",
    "WebhookSubscriptionSummary",
    "WebhooksClient",
    "WorkflowListResponse",
    "WorkflowRegisterResponse",
    "WorkflowSummary",
    "WorkflowsClient",
]
