from typing import Literal
from app.services.llm_intent_resolver import classify_with_gemini

Intent = Literal["free_time", "task", "optimize", "schedule", "general"]


def classify_intent(message: str) -> Intent:
    text = message.lower()

    matches = {
        "free_time": any(k in text for k in ["free", "availability", "available", "slot"]),
        "task": any(k in text for k in ["task", "todo", "to-do", "complete", "mark done"]),
        "optimize": any(k in text for k in ["optimize", "plan my day", "schedule my day", "best plan"]),
        "schedule": any(k in text for k in ["schedule", "meeting", "call", "block", "add event", "calendar"]),
    }

    matched = [name for name, ok in matches.items() if ok]
    if len(matched) == 1:
        return matched[0]  # type: ignore[return-value]

    # For ambiguous or weakly matched prompts, use Gemini fallback when configured.
    if len(matched) != 1 or len(text.split()) <= 3:
        llm_intent = classify_with_gemini(message)
        if llm_intent:
            return llm_intent

    if matches["free_time"]:
        return "free_time"

    if matches["task"]:
        return "task"

    if matches["optimize"]:
        return "optimize"

    if matches["schedule"]:
        return "schedule"

    return "general"
