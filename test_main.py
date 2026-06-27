"""
GymCore AI Services — pytest test suite
========================================

Unit tests for all three FastAPI endpoints:
  - POST /generate-plan
  - POST /analyze-form
  - GET /health

Strategy
--------
- ``AsyncAnthropic`` is monkey-patched at the module level so no real API calls
  are made. Tests inject well-formed or malformed JSON responses and verify that
  the service parses them correctly or falls back as specified.
- ``ANTHROPIC_API_KEY`` is controlled per-test via monkeypatch so we can test
  both the "key present" and "key absent" code paths.
- The ASGI TestClient is synchronous (httpx under the hood), so no asyncio
  event-loop fixtures are needed.
"""

import json
import importlib
import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_message(text: str) -> MagicMock:
    """Build a minimal Anthropic Message mock with one TextBlock."""
    block = MagicMock()
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    return msg


def _valid_plan_json(user_id: str = "user-1", days: int = 3) -> str:
    return json.dumps({
        "user_id": user_id,
        "plan_name": "Test Plan",
        "weekly_plan": [
            {"day": f"Day {i + 1}", "exercise_category": "Strength", "intensity": "Moderate"}
            for i in range(days)
        ],
    })


def _valid_form_json(exercise: str = "Squat") -> str:
    return json.dumps({
        "exercise_name": exercise,
        "overall_score": 8,
        "feedback": [
            {"issue": "Knee caving", "severity": "warning", "correction": "Drive knees out"}
        ],
        "summary": "Good form overall with minor knee tracking issue.",
    })


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_module(monkeypatch: pytest.MonkeyPatch):
    """
    Re-import main.py fresh for each test so that module-level
    ANTHROPIC_API_KEY and ANTHROPIC_MODEL are re-evaluated.
    Yields the freshly imported module.
    """
    import main as m
    # Reset module-level key to None by default (most tests set it explicitly)
    monkeypatch.setattr(m, "ANTHROPIC_API_KEY", None)
    yield m


@pytest.fixture()
def client_no_key(reset_module: Any) -> TestClient:
    """TestClient with no API key set — exercises mock/fallback paths."""
    import main as m
    return TestClient(m.app, raise_server_exceptions=False)


@pytest.fixture()
def client_with_key(reset_module: Any, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient with a fake API key set — exercises real-client paths."""
    import main as m
    monkeypatch.setattr(m, "ANTHROPIC_API_KEY", "sk-test-fake")
    return TestClient(m.app, raise_server_exceptions=False)


# ── GET /health ───────────────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_returns_ok_status(self, client_no_key: TestClient) -> None:
        res = client_no_key.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

    def test_llm_configured_false_when_no_key(self, client_no_key: TestClient) -> None:
        res = client_no_key.get("/health")
        assert res.json()["llm_configured"] is False

    def test_llm_configured_true_when_key_set(self, client_with_key: TestClient) -> None:
        res = client_with_key.get("/health")
        assert res.json()["llm_configured"] is True

    def test_model_field_present(self, client_no_key: TestClient) -> None:
        res = client_no_key.get("/health")
        assert "model" in res.json()


# ── POST /generate-plan — no key (mock path) ──────────────────────────────────

class TestGeneratePlanNoKey:
    BASE_BODY = {
        "user_id": "user-1",
        "fitness_level": "beginner",
        "goal": "lose weight",
        "days_per_week": 3,
    }

    def test_returns_200_with_mock_plan(self, client_no_key: TestClient) -> None:
        res = client_no_key.post("/generate-plan", json=self.BASE_BODY)
        assert res.status_code == 200
        body = res.json()
        assert body["user_id"] == "user-1"
        assert len(body["weekly_plan"]) == 3

    def test_mock_plan_alternates_strength_and_cardio(self, client_no_key: TestClient) -> None:
        res = client_no_key.post("/generate-plan", json={**self.BASE_BODY, "days_per_week": 4})
        days = res.json()["weekly_plan"]
        assert days[0]["exercise_category"] == "Strength"   # Day 1 (odd)
        assert days[1]["exercise_category"] == "Cardio/Mobility"  # Day 2 (even)
        assert days[2]["exercise_category"] == "Strength"   # Day 3 (odd)
        assert days[3]["exercise_category"] == "Cardio/Mobility"  # Day 4 (even)

    def test_mock_plan_advanced_uses_high_intensity(self, client_no_key: TestClient) -> None:
        res = client_no_key.post("/generate-plan", json={**self.BASE_BODY, "fitness_level": "advanced"})
        for day in res.json()["weekly_plan"]:
            assert day["intensity"] == "High"

    def test_mock_plan_non_advanced_uses_moderate_intensity(self, client_no_key: TestClient) -> None:
        for level in ("beginner", "intermediate"):
            res = client_no_key.post("/generate-plan", json={**self.BASE_BODY, "fitness_level": level})
            for day in res.json()["weekly_plan"]:
                assert day["intensity"] == "Moderate"

    def test_mock_plan_name_contains_mock_suffix(self, client_no_key: TestClient) -> None:
        res = client_no_key.post("/generate-plan", json=self.BASE_BODY)
        assert "(Mock)" in res.json()["plan_name"]

    def test_mock_plan_echoes_user_id(self, client_no_key: TestClient) -> None:
        body = {**self.BASE_BODY, "user_id": "uuid-abc-123"}
        res = client_no_key.post("/generate-plan", json=body)
        assert res.json()["user_id"] == "uuid-abc-123"

    def test_days_per_week_validation_min(self, client_no_key: TestClient) -> None:
        res = client_no_key.post("/generate-plan", json={**self.BASE_BODY, "days_per_week": 0})
        assert res.status_code == 422

    def test_days_per_week_validation_max(self, client_no_key: TestClient) -> None:
        res = client_no_key.post("/generate-plan", json={**self.BASE_BODY, "days_per_week": 8})
        assert res.status_code == 422

    def test_missing_required_fields_returns_422(self, client_no_key: TestClient) -> None:
        res = client_no_key.post("/generate-plan", json={"user_id": "x"})
        assert res.status_code == 422


# ── POST /generate-plan — key set (Claude path) ───────────────────────────────

class TestGeneratePlanWithKey:
    BASE_BODY = {
        "user_id": "user-1",
        "fitness_level": "intermediate",
        "goal": "build muscle",
        "days_per_week": 3,
    }

    def test_returns_parsed_claude_response(self, client_with_key: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        import main as m
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=_make_message(_valid_plan_json("user-1", 3)))
        monkeypatch.setattr(m.anthropic, "AsyncAnthropic", MagicMock(return_value=mock_client))

        res = client_with_key.post("/generate-plan", json=self.BASE_BODY)

        assert res.status_code == 200
        body = res.json()
        assert body["user_id"] == "user-1"
        assert body["plan_name"] == "Test Plan"
        assert len(body["weekly_plan"]) == 3

    def test_strips_markdown_code_fences_before_parsing(
        self, client_with_key: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import main as m
        fenced = f"```json\n{_valid_plan_json()}\n```"
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=_make_message(fenced))
        monkeypatch.setattr(m.anthropic, "AsyncAnthropic", MagicMock(return_value=mock_client))

        res = client_with_key.post("/generate-plan", json=self.BASE_BODY)

        assert res.status_code == 200

    def test_falls_back_to_mock_on_json_parse_error(
        self, client_with_key: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import main as m
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=_make_message("not json at all"))
        monkeypatch.setattr(m.anthropic, "AsyncAnthropic", MagicMock(return_value=mock_client))

        res = client_with_key.post("/generate-plan", json=self.BASE_BODY)

        # Should fall back to mock plan rather than returning an error
        assert res.status_code == 200
        assert "(Mock)" in res.json()["plan_name"]

    def test_falls_back_to_mock_on_validation_error(
        self, client_with_key: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import main as m
        # Valid JSON but missing required fields — model_validate will raise
        bad_json = json.dumps({"user_id": "user-1"})
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=_make_message(bad_json))
        monkeypatch.setattr(m.anthropic, "AsyncAnthropic", MagicMock(return_value=mock_client))

        res = client_with_key.post("/generate-plan", json=self.BASE_BODY)

        assert res.status_code == 200
        assert "(Mock)" in res.json()["plan_name"]


# ── POST /analyze-form ────────────────────────────────────────────────────────

class TestAnalyzeForm:
    BASE_BODY = {
        "exercise_name": "Barbell Squat",
        "frames": [{"data": "aGVsbG8=", "media_type": "image/jpeg"}],
    }

    def test_returns_503_when_no_api_key(self, client_no_key: TestClient) -> None:
        res = client_no_key.post("/analyze-form", json=self.BASE_BODY)
        assert res.status_code == 503

    def test_returns_parsed_form_analysis(
        self, client_with_key: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import main as m
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_make_message(_valid_form_json("Barbell Squat"))
        )
        monkeypatch.setattr(m, "_get_client", MagicMock(return_value=mock_client))

        res = client_with_key.post("/analyze-form", json=self.BASE_BODY)

        assert res.status_code == 200
        body = res.json()
        assert body["exercise_name"] == "Barbell Squat"
        assert body["overall_score"] == 8
        assert len(body["feedback"]) == 1
        assert body["feedback"][0]["severity"] == "warning"

    def test_caps_frames_at_4(
        self, client_with_key: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import main as m
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_make_message(_valid_form_json())
        )
        monkeypatch.setattr(m, "_get_client", MagicMock(return_value=mock_client))

        body = {
            "exercise_name": "Squat",
            "frames": [{"data": "aA==", "media_type": "image/jpeg"}] * 6,
        }
        client_with_key.post("/analyze-form", json=body)

        call_args = mock_client.messages.create.call_args
        image_content = call_args.kwargs["messages"][0]["content"]
        # Last item is the text block; everything before is images
        image_blocks = [b for b in image_content if b.get("type") == "image"]
        assert len(image_blocks) == 4

    def test_strips_markdown_fences_from_form_response(
        self, client_with_key: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import main as m
        fenced = f"```json\n{_valid_form_json()}\n```"
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=_make_message(fenced))
        monkeypatch.setattr(m, "_get_client", MagicMock(return_value=mock_client))

        res = client_with_key.post("/analyze-form", json=self.BASE_BODY)

        assert res.status_code == 200

    def test_returns_422_on_json_parse_failure(
        self, client_with_key: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import main as m
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=_make_message("invalid json"))
        monkeypatch.setattr(m, "_get_client", MagicMock(return_value=mock_client))

        res = client_with_key.post("/analyze-form", json=self.BASE_BODY)

        assert res.status_code == 422

    def test_returns_503_on_anthropic_api_error(
        self, client_with_key: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import main as m
        import anthropic as ant

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=ant.APIError(message="rate limited", request=MagicMock(), body={})
        )
        monkeypatch.setattr(m, "_get_client", MagicMock(return_value=mock_client))

        res = client_with_key.post("/analyze-form", json=self.BASE_BODY)

        assert res.status_code == 503

    def test_missing_frames_returns_422(self, client_with_key: TestClient) -> None:
        res = client_with_key.post("/analyze-form", json={"exercise_name": "Squat", "frames": []})
        assert res.status_code == 422

    def test_missing_exercise_name_returns_422(self, client_with_key: TestClient) -> None:
        res = client_with_key.post("/analyze-form", json={"frames": [{"data": "aA==", "media_type": "image/jpeg"}]})
        assert res.status_code == 422
