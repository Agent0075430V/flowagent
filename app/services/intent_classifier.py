import re
from typing import Literal
from app.services.llm_intent_resolver import classify_with_gemini

Intent = Literal["free_time", "task", "optimize", "schedule", "general"]


def classify_intent(message: str) -> Intent:
    text = message.lower()

    has_datetime_hint = bool(
        re.search(
            r"\b(\d{1,2}(:\d{2})?\s?(am|pm)|\d{4}-\d{2}-\d{2}|today|tomorrow|tonight|morning|afternoon|evening|"
            r"january|february|march|april|may|june|july|august|september|october|november|december|"
            r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec|\d{1,2}(st|nd|rd|th))\b",
            text,
        )
    )
    has_scheduling_verb = any(k in text for k in ["schedule", "meeting", "call", "block", "add", "book", "plan"])
    inferred_schedule = has_datetime_hint and has_scheduling_verb

    matches = {
        "free_time": any(k in text for k in ["free", "availability", "available", "slot"]),
        "task": any(k in text for k in ["task", "todo", "to-do", "complete", "mark done"]),
        "optimize": any(k in text for k in ["optimize", "plan my day", "schedule my day", "best plan"]),
        "schedule": any(k in text for k in ["schedule", "meeting", "call", "block", "add event", "calendar"])
        or inferred_schedule,
    }

    matched = [name for name, ok in matches.items() if ok]

    # Unambiguous keyword match on a reasonably long message — return directly.
    if len(matched) == 1 and len(text.split()) > 3:
        return matched[0]  # type: ignore[return-value]

    # For short messages or ambiguous matches, use Gemini when configured.
    llm_intent = classify_with_gemini(message)
    if llm_intent:
        return llm_intent

    # Keyword priority fallback (order matters).
    for intent in ("free_time", "task", "optimize", "schedule"):
        if matches[intent]:
            return intent  # type: ignore[return-value]

    return "general"
