"""
Pydantic data models for the GymCore AI Services API.

These models define the contract between the NestJS backend (caller) and
this FastAPI service (callee). All models carry explicit docstrings so the
auto-generated OpenAPI schema at /docs is self-documenting.

Workout Plan Models
-------------------
UserGoalInput        — Request body for POST /generate-plan.
WorkoutPlanDay       — A single training day within a weekly plan.
WorkoutPlanResponse  — Full response shape persisted to MongoDB by NestJS.

Form Correction Models
----------------------
FormFrame            — One base64-encoded image frame submitted for analysis.
FormAnalysisRequest  — Request body for POST /analyze-form.
FormFeedback         — A single identified issue with its correction.
FormAnalysisResponse — Full form correction report returned to the caller.

Validation Notes
----------------
- ``fitness_level`` accepts 'beginner' | 'intermediate' | 'advanced'.
- ``days_per_week`` is range-gated in NestJS DTO; defence-in-depth via Field(ge=1, le=7).
- ``FormFrame.media_type`` must be a Claude-supported vision MIME type.
"""

from pydantic import BaseModel, Field
from typing import List, Literal, Optional


# ── Workout Plan ─────────────────────────────────────────────────────────────

class UserGoalInput(BaseModel):
    """
    Input payload describing a user's fitness goals for plan generation.

    Attributes:
        user_id:       UUID of the authenticated user (from JWT sub claim).
        fitness_level: Expected values — 'beginner', 'intermediate', 'advanced'.
        goal:          Free-text primary goal, e.g. 'build muscle', 'lose weight'.
        days_per_week: Training days per week, constrained 1–7.
    """

    user_id: str
    fitness_level: str
    goal: str
    days_per_week: int = Field(..., ge=1, le=7)


class WorkoutPlanDay(BaseModel):
    """
    Represents one day's training block within a weekly workout plan.

    Attributes:
        day:               Human-readable day label — 'Day 1', 'Day 2', etc.
        exercise_category: Broad training category — 'Strength', 'Cardio/Mobility', etc.
        intensity:         Perceived exertion — 'Low', 'Moderate', or 'High'.
    """

    day: str
    exercise_category: str
    intensity: Literal["Low", "Moderate", "High"]


class WorkoutPlanResponse(BaseModel):
    """
    Full workout plan response returned to NestJS AiService and persisted to MongoDB.

    Attributes:
        user_id:     Echo of the requesting user UUID for traceability.
        plan_name:   Auto-generated or LLM-generated plan title.
        weekly_plan: Ordered list of WorkoutPlanDay objects, one per training day.
    """

    user_id: str
    plan_name: str
    weekly_plan: List[WorkoutPlanDay]


# ── Form Correction ───────────────────────────────────────────────────────────

class FormFrame(BaseModel):
    """
    A single image frame submitted for form analysis.

    Attributes:
        data:       Base64-encoded raw image data (no data URI prefix).
        media_type: MIME type — must be a Claude vision-supported type.
    """

    data: str
    media_type: Literal["image/jpeg", "image/png", "image/gif", "image/webp"] = "image/jpeg"


class FormAnalysisRequest(BaseModel):
    """
    Request body for POST /analyze-form.

    Callers submit one or more frames of a user performing an exercise. The
    service uses Claude vision to evaluate form and returns structured feedback.

    Attributes:
        exercise_name: Name of the exercise being performed, e.g. 'Barbell Squat'.
        frames:        1–4 image frames. More than 4 is accepted but only the
                       first 4 are sent to Claude to stay within context limits.
        user_id:       Optional user UUID for personalization/logging.
    """

    exercise_name: str
    frames: List[FormFrame] = Field(..., min_length=1)
    user_id: Optional[str] = None


class FormFeedback(BaseModel):
    """
    A single identified form issue with an actionable correction.

    Attributes:
        issue:      Short label for the detected problem, e.g. 'Knee caving inward'.
        severity:   'critical' blocks reps; 'warning' degrades results; 'tip' is minor.
        correction: Specific instruction to fix the issue.
    """

    issue: str
    severity: Literal["critical", "warning", "tip"]
    correction: str


class FormAnalysisResponse(BaseModel):
    """
    Full form correction report returned to the NestJS backend.

    Attributes:
        exercise_name: Echo of the submitted exercise name.
        overall_score: Form quality score 1–10 (10 = perfect technique).
        feedback:      Ordered list of identified issues, most critical first.
        summary:       One-sentence overall assessment for display in the mobile app.
    """

    exercise_name: str
    overall_score: int = Field(..., ge=1, le=10)
    feedback: List[FormFeedback]
    summary: str
