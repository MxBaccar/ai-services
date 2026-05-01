from fastapi import FastAPI
from models import UserGoalInput, WorkoutPlanResponse, WorkoutPlanDay
import uvicorn

app = FastAPI(title="Gym AI Onboarding Service")

@app.post("/generate-plan", response_model=WorkoutPlanResponse)
async def generate_plan(user_input: UserGoalInput):
    # Mock LLM Logic for the "Boss Battle"
    # In production, this would call an LLM (OpenAI/Anthropic) to generate a personalized JSON
    
    mock_days = []
    for i in range(1, user_input.days_per_week + 1):
        category = "Strength" if i % 2 != 0 else "Cardio/Mobility"
        mock_days.append(WorkoutPlanDay(
            day=f"Day {i}",
            exercise_category=category,
            intensity="High" if user_input.fitness_level == "advanced" else "Moderate"
        ))
    
    return WorkoutPlanResponse(
        user_id=user_input.user_id,
        plan_name=f"{user_input.goal.capitalize()} Phase 1",
        weekly_plan=mock_days
    )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
