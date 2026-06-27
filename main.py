"""
GymCore AI Services — FastAPI Microservice
==========================================

Provides AI-powered workout planning capabilities for the GymCore ecosystem.
Called exclusively by the NestJS backend (ai.service.ts) via internal Docker network.

Current Endpoints
-----------------
POST /generate-plan
    Receives a user goal payload and returns a structured weekly workout plan.
    STATUS: Mock implementation. No real LLM calls are made.

Pending Endpoints
-----------------
POST /analyze-form
    Accept a video/image URL, run pose estimation, return form correction feedback.
    Blocked by: model selection (MediaPipe / OpenPose), infrastructure for GPU inference.

GET /health
    Health check for Docker Compose depends_on healthcheck configuration.

Architecture Notes
------------------
- This service is not exposed to the public internet. It runs on the internal
  `gym_network` Docker bridge and is accessed at http://ai-services:8000 by NestJS.
- Workout plans are returned as JSON and persisted to MongoDB by the NestJS ai.service.
- In production, the mock logic in generate_plan() should be replaced with a call
  to an LLM (Anthropic Claude / OpenAI) using the user goal as a structured prompt.
"""

from fastapi import FastAPI
from models import UserGoalInput, WorkoutPlanResponse, WorkoutPlanDay
import uvicorn

app = FastAPI(
    title="GymCore AI Services",
    description="Internal AI microservice for workout plan generation and form correction.",
    version="0.1.0",
)


@app.post("/generate-plan", response_model=WorkoutPlanResponse)
async def generate_plan(user_input: UserGoalInput) -> WorkoutPlanResponse:
    """
    Generate a personalized weekly workout plan based on user fitness goals.

    This endpoint is called by NestJS ``AiService.onboardUser()`` during the
    mobile app onboarding flow.

    Args:
        user_input: Validated ``UserGoalInput`` containing user_id, fitness_level,
                    goal string, and days_per_week (1–7).

    Returns:
        ``WorkoutPlanResponse`` with a plan_name and a list of ``WorkoutPlanDay``
        objects, one per requested training day.

    Note:
        Current implementation is a deterministic mock. Odd days are assigned
        Strength training; even days are assigned Cardio/Mobility. Intensity is
        set to "High" for advanced users and "Moderate" for all others.

        TODO: Replace mock logic with an LLM call (e.g. Anthropic Claude) that
        generates a genuinely personalized, exercise-specific plan in JSON format.
    """
    mock_days = []
    for i in range(1, user_input.days_per_week + 1):
        category = "Strength" if i % 2 != 0 else "Cardio/Mobility"
        mock_days.append(
            WorkoutPlanDay(
                day=f"Day {i}",
                exercise_category=category,
                intensity="High" if user_input.fitness_level == "advanced" else "Moderate",
            )
        )

    return WorkoutPlanResponse(
        user_id=user_input.user_id,
        plan_name=f"{user_input.goal.capitalize()} Phase 1",
        weekly_plan=mock_days,
    )


@app.get("/health")
async def health_check() -> dict:
    """
    Liveness probe endpoint for Docker Compose healthcheck and Prometheus scraping.

    Returns:
        JSON object ``{"status": "ok"}`` when the service is running.
    """
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
