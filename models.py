"""
Pydantic data models for the GymCore AI Services API.

These models define the contract between the NestJS backend (caller) and
this FastAPI service (callee). They map directly to the NestJS ``UserGoalDto``
and the ``WorkoutPlanResponse`` shape stored in MongoDB.

Classes
-------
UserGoalInput
    Request body for POST /generate-plan.
    Mirrors the NestJS UserGoalDto shape.

WorkoutPlanDay
    A single training day within a weekly plan.

WorkoutPlanResponse
    Full response shape for POST /generate-plan.
    Persisted as a MongoDB document by NestJS AiService.

Validation Notes
----------------
- ``fitness_level`` is an unconstrained string. Consider using a Literal type
  ('beginner' | 'intermediate' | 'advanced') once the contract is stable.
- ``days_per_week`` range (1–7) is enforced in the NestJS DTO but not here.
  Add a Pydantic Field(ge=1, le=7) constraint for defence-in-depth.
"""

from pydantic import BaseModel
from typing import List


class UserGoalInput(BaseModel):
    """
    Input payload describing a user's fitness goals for plan generation.

    Attributes:
        user_id: The UUID of the authenticated user (sourced from JWT sub claim).
        fitness_level: Skill level string — expected values: 'beginner',
                       'intermediate', 'advanced'.
        goal: Free-text description of the user's primary goal,
              e.g. 'build muscle', 'lose weight', 'improve endurance'.
        days_per_week: Number of training days per week (1–7).
    """

    user_id: str
    fitness_level: str
    goal: str
    days_per_week: int


class WorkoutPlanDay(BaseModel):
    """
    Represents a single day's training block within a weekly workout plan.

    Attributes:
        day: Human-readable day label, e.g. 'Day 1', 'Day 2'.
        exercise_category: Broad training category for the day,
                           e.g. 'Strength', 'Cardio/Mobility'.
        intensity: Perceived exertion descriptor — 'High', 'Moderate', or 'Low'.
    """

    day: str
    exercise_category: str
    intensity: str


class WorkoutPlanResponse(BaseModel):
    """
    Full workout plan response returned to the NestJS AiService.

    This object is serialized and stored as-is in the MongoDB WorkoutPlan
    collection under the ``plan`` field (Mixed type).

    Attributes:
        user_id: Echo of the requesting user's UUID for traceability.
        plan_name: Auto-generated plan title, e.g. 'Build Muscle Phase 1'.
        weekly_plan: Ordered list of WorkoutPlanDay objects.
    """

    user_id: str
    plan_name: str
    weekly_plan: List[WorkoutPlanDay]
