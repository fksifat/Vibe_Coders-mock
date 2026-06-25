# QueueStorm Ticket Classifier

**bKash · SUST CSE Carnival 2026 · Hackathon Mock Preliminary**

A FastAPI web service that reads one customer CRM message and returns a structured classification — case type, severity, department, agent summary, human-review flag, and confidence score — using the **Google Gemini** LLM with a rule-based fallback.

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service health check |
| `POST` | `/sort-ticket` | Classify a CRM support ticket |

Interactive API docs available at `/docs` when running locally.

---

## Quick Start (Local)

### 1. Clone & enter the repo

```bash
git clone <your-repo-url>
cd Sust_hackathon
```

### 2. Create a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up environment variables

```bash
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

Get your free API key at: https://aistudio.google.com/app/apikey

### 5. Run the server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The service will be available at `http://localhost:8000`.

---

## Example Request

```bash
curl -X POST http://localhost:8000/sort-ticket \
  -H "Content-Type: application/json" \
  -d '{
    "ticket_id": "T-001",
    "channel": "app",
    "locale": "en",
    "message": "I sent 5000 taka to a wrong number this morning, please help me get it back"
  }'
```

### Example Response

```json
{
  "ticket_id": "T-001",
  "case_type": "wrong_transfer",
  "severity": "high",
  "department": "dispute_resolution",
  "agent_summary": "Customer reports sending 5000 BDT to an unintended recipient and requests recovery assistance.",
  "human_review_required": true,
  "confidence": 0.92
}
```

---

## Deployment (Render)

1. Push the repo to GitHub (ensure `.env` is in `.gitignore`)
2. Create a new **Web Service** on [Render](https://render.com)
3. Set **Build Command**: `pip install -r requirements.txt`
4. Set **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add the environment variable `GEMINI_API_KEY` in Render's dashboard
6. Deploy — Render provides a free HTTPS URL automatically

---

## Architecture

```
POST /sort-ticket
       │
       ▼
  TicketRequest (Pydantic validation)
       │
       ▼
  classifier.classify_ticket()
       ├── Gemini 2.0 Flash (primary)
       │       └── Structured JSON prompt → parse → validate
       └── Rule-based fallback (if Gemini unavailable)
       │
       ▼
  _validate_and_sanitize()   ← enforces enum values + safety rule
       │
       ▼
  TicketResponse (Pydantic)
       │
       ▼
  JSON response to client
```

### Safety Rule
The `agent_summary` is scanned for forbidden terms (`pin`, `otp`, `password`, `card number`). If found, the summary is replaced with a safe default and a warning is logged.

---

## LLM Details

- **Model**: `gemini-2.0-flash`
- **Temperature**: 0.1 (low, for consistent output)
- **Fallback**: Keyword-based rule engine (no API required)
- **No GPU** dependency

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Yes | Google Gemini API key |
| `HOST` | No | Bind host (default: `0.0.0.0`) |
| `PORT` | No | Port (default: `8000`) |

> **Never commit your `.env` file or API key to version control.**
