"""
GymCore AI Services — FastAPI Microservice
==========================================

Provides AI-powered capabilities for the GymCore ecosystem via the Anthropic
Claude API. Called exclusively by the NestJS backend over the internal Docker
network (``http://ai-services:8000``).

Endpoints
---------
POST /generate-plan
    Generates a personalized weekly workout plan using Claude claude-sonnet-4-6.
    Falls back to a deterministic mock when ``ANTHROPIC_API_KEY`` is not set,
    so the service stays healthy in local development without an API key.

POST /analyze-form
    Accepts 1–4 base64 image frames of a user performing an exercise and returns
    structured form-correction feedback via Claude vision (claude-sonnet-4-6).

GET /health
    Liveness probe for Docker Compose ``depends_on`` healthcheck.

Environment Variables
---------------------
ANTHROPIC_API_KEY   — Required for real LLM calls. If absent, /generate-plan
                      uses the deterministic mock and /analyze-form returns a
                      503 (vision cannot fall back meaningfully).
ANTHROPIC_MODEL     — Override the Claude model. Default: claude-sonnet-4-6.

Architecture Notes
------------------
- Workout plans are returned as JSON and persisted to MongoDB by NestJS ai.service.
- All Claude calls use ``AsyncAnthropic`` so the FastAPI event loop is never blocked.
- JSON responses from Claude are parsed and validated by Pydantic. If parsing fails,
  /generate-plan falls back to the deterministic mock; /analyze-form raises 422.
"""

import json
import logging
import os
from typing import Optional

import anthropic
from fastapi import FastAPI, HTTPException
from models import (
    FormAnalysisRequest,
    FormAnalysisResponse,
    FormFeedback,
    UserGoalInput,
    WorkoutPlanDay,
    WorkoutPlanResponse,
)

logger = logging.getLogger("gymcore.ai")

ANTHROPIC_API_KEY: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

app = FastAPI(
    title="GymCore AI Services",
    description="Internal AI microservice for workout plan generation and form correction.",
    version="0.2.0",
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_client() -> anthropic.AsyncAnthropic:
    """Return a configured Anthropic async client. Raises 503 if key is missing."""
    if not ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=503,
            detail={"errorKey": "ai.errors.service_unavailable"},
        )
    return anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)


def _mock_plan(user_input: UserGoalInput) -> WorkoutPlanResponse:
    """
    Deterministic fallback plan used when ``ANTHROPIC_API_KEY`` is not configured.

    Alternates Strength / Cardio–Mobility by day; sets intensity based on
    fitness_level. Allows local development and CI to run without an API key.
    """
    days = []
    for i in range(1, user_input.days_per_week + 1):
        category = "Strength" if i % 2 != 0 else "Cardio/Mobility"
        intensity = "High" if user_input.fitness_level == "advanced" else "Moderate"
        days.append(WorkoutPlanDay(day=f"Day {i}", exercise_category=category, intensity=intensity))

    return WorkoutPlanResponse(
        user_id=user_input.user_id,
        plan_name=f"{user_input.goal.capitalize()} Phase 1 (Mock)",
        weekly_plan=days,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/generate-plan", response_model=WorkoutPlanResponse)
async def generate_plan(user_input: UserGoalInput) -> WorkoutPlanResponse:
    """
    Generate a personalized weekly workout plan based on user fitness goals.

    Called by NestJS ``AiService.onboardUser()`` during the mobile app
    onboarding flow. Uses Claude claude-sonnet-4-6 to produce a day-by-day plan that
    matches the user's fitness level and primary goal.

    Falls back to a deterministic mock when ``ANTHROPIC_API_KEY`` is absent so
    the service remains usable in local development without spending API credits.

    Args:
        user_input: Validated ``UserGoalInput`` — user_id, fitness_level,
                    goal string, and days_per_week (1–7).

    Returns:
        ``WorkoutPlanResponse`` with a plan_name and ordered ``WorkoutPlanDay`` list.

    Raises:
        HTTPException(422): If Claude returns malformed JSON that cannot be
                            parsed into ``WorkoutPlanResponse`` (after mock fallback).
    """
    if not ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set — returning deterministic mock plan.")
        return _mock_plan(user_input)

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    system_prompt = f"""You are an expert personal trainer with 20 years of experience.
Your task is to create a structured weekly workout plan for a user.

CRITICAL: Respond with ONLY a valid JSON object. No explanatory text, no markdown
code fences, no additional commentary — ONLY the raw JSON object.

The JSON MUST match this exact schema:
{{
  "user_id": "<string — echo the provided user_id exactly>",
  "plan_name": "<string — a creative, motivating plan name, max 60 chars>",
  "weekly_plan": [
    {{
      "day": "<string — e.g. 'Day 1'>",
      "exercise_category": "<string — e.g. 'Upper Body Strength', 'HIIT Cardio', 'Lower Body & Core'>",
      "intensity": "<exactly one of: Low | Moderate | High>"
    }}
  ]
}}

The weekly_plan array MUST contain exactly {user_input.days_per_week} items.
Intensity values must be exactly 'Low', 'Moderate', or 'High' — no other values accepted."""

    user_message = (
        f"Create a workout plan for this user:\n"
        f"- User ID: {user_input.user_id}\n"
        f"- Fitness Level: {user_input.fitness_level}\n"
        f"- Primary Goal: {user_input.goal}\n"
        f"- Training Days Per Week: {user_input.days_per_week}\n\n"
        f"Generate exactly {user_input.days_per_week} days in the weekly_plan array."
    )

    try:
        message = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

        raw_json = message.content[0].text.strip()

        # Strip accidental markdown code fences if Claude adds them despite instructions
        if raw_json.startswith("```"):
            raw_json = raw_json.split("```")[1]
            if raw_json.startswith("json"):
                raw_json = raw_json[4:]
            raw_json = raw_json.strip()

        plan_data = json.loads(raw_json)
        return WorkoutPlanResponse.model_validate(plan_data)

    except (json.JSONDecodeError, Exception) as exc:
        logger.error("Claude response parse failed — falling back to mock. Error: %s", exc)
        return _mock_plan(user_input)


@app.post("/analyze-form", response_model=FormAnalysisResponse)
async def analyze_form(request: FormAnalysisRequest) -> FormAnalysisResponse:
    """
    Analyze exercise form from one or more image frames using Claude vision.

    Accepts base64-encoded image frames of a user performing an exercise and
    returns structured feedback identifying form issues, their severity, and
    specific corrections. Frames beyond the first 4 are silently dropped to
    stay within Claude's context limits.

    Args:
        request: ``FormAnalysisRequest`` containing exercise_name and frame list.

    Returns:
        ``FormAnalysisResponse`` with overall_score (1–10), per-issue feedback,
        and a one-sentence summary.

    Raises:
        HTTPException(503): ``ANTHROPIC_API_KEY`` is not configured.
        HTTPException(422): Claude returns a response that cannot be parsed
                            into the expected JSON structure.
    """
    client = _get_client()  # Raises 503 if no API key

    # Cap at 4 frames to respect Claude's context window and cost
    frames = request.frames[:4]

    # Build the vision content block list — one image per frame
    image_content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": frame.media_type,
                "data": frame.data,
            },
        }
        for frame in frames
    ]

    # Append the instruction text after the images
    image_content.append(
        {
            "type": "text",
            "text": (
                f"These {len(frames)} image frame(s) show a person performing the "
                f"'{request.exercise_name}' exercise. Analyse their form."
            ),
        }
    )

    system_prompt = """You are an elite strength and conditioning coach specialising in
exercise technique and injury prevention.

Analyse the provided image frames of an athlete performing an exercise. Identify any
form issues, rank them by severity, and provide specific, actionable corrections.

CRITICAL: Respond with ONLY a valid JSON object — no text before or after, no markdown fences.

The JSON MUST match this exact schema:
{
  "exercise_name": "<echo the exercise name provided>",
  "overall_score": <integer 1–10, where 10 is perfect technique>,
  "feedback": [
    {
      "issue": "<short label for the detected problem>",
      "severity": "<exactly one of: critical | warning | tip>",
      "correction": "<specific, actionable instruction to fix it>"
    }
  ],
  "summary": "<one sentence overall assessment suitable for display in a mobile app>"
}

Severity definitions:
  critical — immediate injury risk; must be corrected before continuing
  warning  — degrades results or increases long-term injury risk
  tip      — minor improvement that would enhance efficiency or aesthetics

If the form is excellent, return an empty feedback array and a high overall_score."""

    try:
        message = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": image_content}],
        )

        raw_json = message.content[0].text.strip()

        if raw_json.startswith("```"):
            raw_json = raw_json.split("```")[1]
            if raw_json.startswith("json"):
                raw_json = raw_json[4:]
            raw_json = raw_json.strip()

        response_data = json.loads(raw_json)
        return FormAnalysisResponse.model_validate(response_data)

    except json.JSONDecodeError as exc:
        logger.error("Form analysis JSON parse failed: %s", exc)
        raise HTTPException(
            status_code=422,
            detail={"errorKey": "ai.errors.form_analysis_parse_failed"},
        )
    except anthropic.APIError as exc:
        logger.error("Anthropic API error during form analysis: %s", exc)
        raise HTTPException(
            status_code=503,
            detail={"errorKey": "ai.errors.service_unavailable"},
        )


@app.get("/health")
async def health_check() -> dict:
    """
    Liveness probe for Docker Compose healthcheck and Prometheus scraping.

    Returns:
        JSON ``{"status": "ok", "llm_configured": bool}`` — the llm_configured
        flag lets ops dashboards detect misconfigured deployments at a glance.
    """
    return {
        "status": "ok",
        "llm_configured": ANTHROPIC_API_KEY is not None,
        "model": ANTHROPIC_MODEL,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
