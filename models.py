from pydantic import BaseModel
from typing import List

class UserGoalInput(BaseModel):
    user_id: str
    fitness_level: str
    goal: str
    days_per_week: int

class WorkoutPlanDay(BaseModel):
    day: str
    exercise_category: str
    intensity: str

class WorkoutPlanResponse(BaseModel):
    user_id: str
    plan_name: str
    weekly_plan: List[WorkoutPlanDay]
