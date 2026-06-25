import logging
import time
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()  # Load .env before any module reads environment variables

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from models import TicketRequest, TicketResponse, HealthResponse
from classifier import classify_ticket

# ─── Logging setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ─── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("QueueStorm Ticket Classifier starting up...")
    yield
    logger.info("QueueStorm Ticket Classifier shutting down.")


# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="QueueStorm Ticket Classifier",
    description=(
        "A CRM ticket triage service for bKash / digital finance support. "
        "Classifies customer messages by case type, severity, and department "
        "using the Gemini LLM with a rule-based fallback."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Middleware: request timing ───────────────────────────────────────────────
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    response.headers["X-Process-Time"] = f"{elapsed:.4f}s"
    logger.info("%s %s — %.4fs", request.method, request.url.path, elapsed)
    return response


# ─── Routes ───────────────────────────────────────────────────────────────────
@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    tags=["Health"],
)
async def health():
    """Return a simple health status for the service."""
    return HealthResponse()


@app.post(
    "/sort-ticket",
    response_model=TicketResponse,
    summary="Classify a CRM support ticket",
    tags=["Tickets"],
)
async def sort_ticket(ticket: TicketRequest):
    """
    Accept a customer CRM ticket and return a structured classification
    including case type, severity, department assignment, agent summary,
    human review flag, and a confidence score.
    """
    if not ticket.message or not ticket.message.strip():
        raise HTTPException(status_code=422, detail="Field 'message' must not be empty.")

    logger.info("Processing ticket_id=%s  channel=%s  locale=%s", ticket.ticket_id, ticket.channel, ticket.locale)

    result = await classify_ticket(
        message=ticket.message.strip(),
        channel=ticket.channel.value if ticket.channel else None,
        locale=ticket.locale.value if ticket.locale else None,
    )

    # Determine human_review_required from classification result
    human_review = (
        result["severity"] == "critical"
        or result["case_type"] == "phishing_or_social_engineering"
    )

    response = TicketResponse(
        ticket_id=ticket.ticket_id,
        case_type=result["case_type"],
        severity=result["severity"],
        department=result["department"],
        agent_summary=result["agent_summary"],
        human_review_required=human_review,
        confidence=result["confidence"],
    )

    logger.info(
        "ticket_id=%s → case_type=%s  severity=%s  human_review=%s",
        ticket.ticket_id,
        response.case_type,
        response.severity,
        response.human_review_required,
    )
    return response


# ─── Global error handler ─────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again."},
    )
