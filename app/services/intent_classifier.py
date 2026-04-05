from typing import Literal

Intent = Literal["free_time", "task", "optimize", "schedule", "general"]


def classify_intent(message: str) -> Intent:
    text = message.lower()

    if any(k in text for k in ["free", "availability", "available", "slot"]):
        return "free_time"

    if any(k in text for k in ["task", "todo", "to-do", "complete", "mark done"]):
        return "task"

    if any(k in text for k in ["optimize", "plan my day", "schedule my day", "best plan"]):
        return "optimize"

    if any(k in text for k in ["schedule", "meeting", "call", "block", "add event", "calendar"]):
        return "schedule"

    return "general"
