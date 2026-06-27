# GymCore AI Services — Python FastAPI

Internal AI microservice providing workout plan generation and exercise form correction via the Anthropic Claude API. Called exclusively by the NestJS backend over the internal Docker network.

> **Pending work & known issues** are tracked in [`ECOSYSTEM_PLANNING.md`](../../ECOSYSTEM_PLANNING.md) at the monorepo root.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI (async) |
| LLM | Anthropic Claude (`claude-sonnet-4-6`) via `anthropic` SDK |
| Validation | Pydantic v2 |
| Type checking | mypy (strict mode — see `mypy.ini`) |
| HTTP server | Uvicorn |

---

## Architecture

```
apps/ai-services/
├── main.py        # FastAPI app — endpoints, LLM calls, mock fallback
├── models.py      # Pydantic request/response models
├── requirements.txt
└── mypy.ini       # strict = True, ignore_missing_imports = True
```

**Service boundary:** This service is not publicly reachable. NestJS proxies requests to it over the internal `gym_network` Docker bridge (`http://ai-services:8000`).

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/generate-plan` | Generate personalized weekly workout plan (JSON response) |
| `POST` | `/analyze-form` | Analyze exercise form from base64 image frames |
| `GET` | `/health` | Liveness probe — returns `{ status, llm_configured, model }` |

### `POST /generate-plan`

```json
{
  "user_id": "uuid",
  "fitness_level": "beginner | intermediate | advanced",
  "goal": "string",
  "days_per_week": 1
}
```

Falls back to a deterministic mock plan when `ANTHROPIC_API_KEY` is absent — the service never returns an error for missing credentials on this endpoint.

### `POST /analyze-form`

```json
{
  "exercise_name": "Barbell Squat",
  "frames": [
    { "data": "<base64>", "media_type": "image/jpeg" }
  ],
  "user_id": "uuid (optional)"
}
```

Accepts up to 4 frames. Returns `overall_score` (1–10), per-issue `feedback` with `severity` (`critical | warning | tip`), and a one-sentence `summary`. Returns **503** when `ANTHROPIC_API_KEY` is absent (no meaningful vision fallback).

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | API key for Claude. When absent, `/generate-plan` uses mock; `/analyze-form` returns 503 |
| `ANTHROPIC_MODEL` | — | Model override (default: `claude-sonnet-4-6`) |

---

## How to Run

### With Docker Compose (recommended)

```bash
# From the monorepo root:
docker compose up ai-services
```

### Local Development

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Health check:

```bash
curl http://localhost:8000/health
# → { "status": "ok", "llm_configured": false, "model": "claude-sonnet-4-6" }
```

---

## Type Checking

```bash
pip install mypy
mypy main.py models.py
# All functions must be fully typed — no bare dict, list, or Any returns.
# See mypy.ini for the full strict configuration.
```

---

## Mock Fallback

When `ANTHROPIC_API_KEY` is not set, `generate_plan()` returns a deterministic plan:
- Alternates Strength / Cardio-Mobility by day.
- Intensity set to `"High"` for `advanced`, `"Moderate"` otherwise.
- `plan_name` is suffixed with `(Mock)` so callers can detect the fallback in logs.

This keeps the full Docker stack functional in local development without spending API credits.
