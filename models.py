from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum


class ChannelEnum(str, Enum):
    app = "app"
    sms = "sms"
    call_center = "call_center"
    merchant_portal = "merchant_portal"


class LocaleEnum(str, Enum):
    bn = "bn"
    en = "en"
    mixed = "mixed"


class CaseTypeEnum(str, Enum):
    wrong_transfer = "wrong_transfer"
    payment_failed = "payment_failed"
    refund_request = "refund_request"
    phishing_or_social_engineering = "phishing_or_social_engineering"
    other = "other"


class SeverityEnum(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class DepartmentEnum(str, Enum):
    customer_support = "customer_support"
    dispute_resolution = "dispute_resolution"
    payments_ops = "payments_ops"
    fraud_risk = "fraud_risk"


class TicketRequest(BaseModel):
    ticket_id: str = Field(..., description="Unique ticket identifier")
    channel: Optional[ChannelEnum] = Field(None, description="Channel the ticket came from")
    locale: Optional[LocaleEnum] = Field(None, description="Language locale of the message")
    message: str = Field(..., description="Free text customer complaint")


class TicketResponse(BaseModel):
    ticket_id: str = Field(..., description="Echoed ticket ID from request")
    case_type: CaseTypeEnum = Field(..., description="Classified type of the issue")
    severity: SeverityEnum = Field(..., description="Severity level of the issue")
    department: DepartmentEnum = Field(..., description="Department that should handle this ticket")
    agent_summary: str = Field(..., description="One or two neutral sentences for the agent")
    human_review_required: bool = Field(..., description="True for critical severity or phishing cases")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Model confidence score between 0 and 1")


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "QueueStorm Ticket Classifier"
    version: str = "1.0.0"
