from typing import Literal

from langchain_google_vertexai import ChatVertexAI

from app.config import get_settings

Intent = Literal["free_time", "task", "optimize", "schedule", "general"]

_ALLOWED = {"free_time", "task", "optimize", "schedule", "general"}


def classify_with_gemini(message: str) -> Intent | None:
    settings = get_settings()
    if not settings.use_gemini_intent_fallback:
        return None

    project = settings.gemini_project_id or settings.gcp_project_id
    if not project:
        return None

    model = ChatVertexAI(
        model_name=settings.gemini_model,
        project=project,
        location=settings.gemini_location,
        temperature=0,
        max_output_tokens=8,
    )

    prompt = (
        "Classify the user message into exactly one label from: "
        "free_time, task, optimize, schedule, general. "
        "Return only the label and nothing else.\n"
        f"Message: {message}"
    )

    try:
        result = model.invoke(prompt)
        label = str(result.content).strip().lower()
        return label if label in _ALLOWED else None
    except Exception:
        return None
