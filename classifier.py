import os
import json
import re
import logging
from typing import Optional
import google.generativeai as genai
from models import CaseTypeEnum, SeverityEnum, DepartmentEnum

logger = logging.getLogger(__name__)

# Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

CLASSIFICATION_PROMPT = """
You are a CRM ticket classifier for a digital mobile financial service (like bKash in Bangladesh).
Analyze the customer message and return a JSON object with exactly these fields.

Customer message: "{message}"
Channel: {channel}
Locale: {locale}

Classify this ticket and respond ONLY with a valid JSON object (no markdown, no explanation):

{{
  "case_type": "<one of: wrong_transfer | payment_failed | refund_request | phishing_or_social_engineering | other>",
  "severity": "<one of: low | medium | high | critical>",
  "department": "<one of: customer_support | dispute_resolution | payments_ops | fraud_risk>",
  "agent_summary": "<one or two neutral sentences describing the issue for a support agent. NEVER ask for PIN, OTP, password, or card number>",
  "confidence": <float between 0.0 and 1.0>
}}

Classification rules:
- wrong_transfer: money sent to wrong recipient → department: dispute_resolution, severity: high
- payment_failed: transaction failed, balance possibly deducted → department: payments_ops, severity: high
- refund_request: customer wants a refund → department: customer_support (low) or dispute_resolution (contested), severity: low or medium
- phishing_or_social_engineering: suspicious calls/SMS, asking for PIN/OTP/password → department: fraud_risk, severity: critical
- other: anything else → department: customer_support, severity: low

Severity escalation:
- critical: always for phishing/social engineering, or if financial fraud is imminent
- high: for wrong_transfer and payment_failed
- medium: for contested refunds or unclear issues
- low: for general queries, app bugs, minor refund requests

The agent_summary must be factual, neutral, and safe. NEVER write the words PIN, OTP, password, or card number in the agent_summary field — describe the situation without quoting those terms (e.g. say "sensitive credentials" instead).
"""


# ─── Fallback rule-based classifier ──────────────────────────────────────────

PHISHING_KEYWORDS = [
    "otp", "pin", "password", "verification code", "verify your account",
    "share your", "told me to share", "someone called", "called asking",
    "asked for my otp", "asked for my pin", "someone asked",
    "security code", "একটি কোড", "পিন", "ওটিপি"
]

WRONG_TRANSFER_KEYWORDS = [
    "wrong number", "wrong account", "wrong recipient", "sent to wrong",
    "ভুল নম্বর", "wrong transfer", "mistakenly sent", "accidentally sent"
]

PAYMENT_FAILED_KEYWORDS = [
    "payment failed", "transaction failed", "balance deducted", "failed but",
    "money deducted", "deducted but", "not received", "পেমেন্ট ফেল", "ব্যালেন্স কাটা"
]

REFUND_KEYWORDS = [
    "refund", "money back", "return my money", "cancel", "ফেরত", "রিফান্ড"
]


def rule_based_classify(message: str) -> dict:
    """Fallback rule-based classifier when Gemini is unavailable."""
    msg_lower = message.lower()

    if any(kw in msg_lower for kw in PHISHING_KEYWORDS):
        return {
            "case_type": "phishing_or_social_engineering",
            "severity": "critical",
            "department": "fraud_risk",
            "agent_summary": "Customer reports a suspicious contact attempting to obtain sensitive account credentials. Immediate fraud team review required.",
            "confidence": 0.82,
        }

    if any(kw in msg_lower for kw in WRONG_TRANSFER_KEYWORDS):
        return {
            "case_type": "wrong_transfer",
            "severity": "high",
            "department": "dispute_resolution",
            "agent_summary": "Customer reports sending money to an unintended recipient and requests assistance with recovery.",
            "confidence": 0.85,
        }

    if any(kw in msg_lower for kw in PAYMENT_FAILED_KEYWORDS):
        return {
            "case_type": "payment_failed",
            "severity": "high",
            "department": "payments_ops",
            "agent_summary": "Customer reports a failed transaction with a possible balance deduction. Requires payment operations review.",
            "confidence": 0.80,
        }

    if any(kw in msg_lower for kw in REFUND_KEYWORDS):
        return {
            "case_type": "refund_request",
            "severity": "low",
            "department": "customer_support",
            "agent_summary": "Customer is requesting a refund for a recent transaction.",
            "confidence": 0.78,
        }

    return {
        "case_type": "other",
        "severity": "low",
        "department": "customer_support",
        "agent_summary": "Customer has raised a general support inquiry that requires review by the customer support team.",
        "confidence": 0.65,
    }


def _parse_gemini_response(text: str) -> Optional[dict]:
    """Extract and parse JSON from Gemini's response text."""
    # Strip markdown code fences if present
    text = re.sub(r"```(?:json)?", "", text).strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to extract first JSON object
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


def _validate_and_sanitize(data: dict) -> dict:
    """Validate enum values and enforce safety rules."""
    valid_case_types = {e.value for e in CaseTypeEnum}
    valid_severities = {e.value for e in SeverityEnum}
    valid_departments = {e.value for e in DepartmentEnum}

    case_type = data.get("case_type", "other")
    if case_type not in valid_case_types:
        case_type = "other"

    severity = data.get("severity", "low")
    if severity not in valid_severities:
        severity = "low"

    department = data.get("department", "customer_support")
    if department not in valid_departments:
        department = "customer_support"

    # Enforce business rules
    if case_type == "phishing_or_social_engineering":
        severity = "critical"
        department = "fraud_risk"

    # Safety rule: sanitize agent_summary
    summary = data.get("agent_summary", "Customer has submitted a support ticket requiring review.")
    forbidden = ["pin", "otp", "password", "card number", "full card"]
    for term in forbidden:
        if term in summary.lower():
            summary = "Customer has submitted a support ticket. Please review the details carefully."
            logger.warning("Safety rule triggered: forbidden term in agent_summary, replaced.")
            break

    # Clamp confidence
    try:
        confidence = float(data.get("confidence", 0.75))
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.75

    return {
        "case_type": case_type,
        "severity": severity,
        "department": department,
        "agent_summary": summary,
        "confidence": confidence,
    }


async def classify_ticket(
    message: str,
    channel: Optional[str] = None,
    locale: Optional[str] = None,
) -> dict:
    """
    Classify a CRM ticket using Gemini. Falls back to rule-based
    classification if Gemini is unavailable or returns an invalid response.
    """
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set — using rule-based fallback.")
        return rule_based_classify(message)

    prompt = CLASSIFICATION_PROMPT.format(
        message=message,
        channel=channel or "unknown",
        locale=locale or "unknown",
    )

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,        # Low temperature for consistent output
                max_output_tokens=512,
            ),
        )
        raw_text = response.text
        logger.debug("Gemini raw response: %s", raw_text)

        parsed = _parse_gemini_response(raw_text)
        if parsed is None:
            logger.warning("Could not parse Gemini response, using rule-based fallback.")
            return rule_based_classify(message)

        return _validate_and_sanitize(parsed)

    except Exception as exc:
        logger.error("Gemini API error: %s — falling back to rule-based.", exc)
        return rule_based_classify(message)
