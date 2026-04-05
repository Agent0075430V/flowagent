import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dateparser import parse as parse_date

from app.services.calendar_agent import CalendarAgent


class SchedulingAgent:
    def __init__(self) -> None:
        self.calendar = CalendarAgent()

    @staticmethod
    def _extract_duration_minutes(message: str) -> int:
        text = message.lower()
        m = re.search(r"(\d+)\s*(minute|minutes|min)", text)
        if m:
            return int(m.group(1))
        h = re.search(r"(\d+)\s*(hour|hours|hr|hrs)", text)
        if h:
            return int(h.group(1)) * 60
        return 60

    @staticmethod
    def _extract_title(message: str) -> str:
        cleaned = re.sub(r"\s+", " ", message).strip()
        for prefix in ["schedule", "add", "block", "find me", "create"]:
            if cleaned.lower().startswith(prefix):
                cleaned = cleaned[len(prefix):].strip(" :")
                break
        if len(cleaned) > 80:
            cleaned = cleaned[:80]
        return cleaned.title() if cleaned else "Focus Session"

    @staticmethod
    def _to_ampm(dt: datetime) -> str:
        return dt.strftime("%I:%M %p").lstrip("0")

    def propose_slot(self, user_id: str, message: str) -> dict:
        events, tz = self.calendar.get_today_events(user_id)
        _ = events  # ensures fresh calendar read before schedule answers

        duration = self._extract_duration_minutes(message)
        title = self._extract_title(message)
        local_tz = ZoneInfo(tz)
        now = datetime.now(local_tz)

        parsed = parse_date(
            message,
            settings={
                "TIMEZONE": tz,
                "TO_TIMEZONE": tz,
                "RETURN_AS_TIMEZONE_AWARE": True,
                "PREFER_DATES_FROM": "future",
            },
        )

        if parsed and "before noon" not in message.lower() and "sometime" not in message.lower():
            start = parsed.astimezone(local_tz)
            end = start + timedelta(minutes=duration)
            free_slots, _ = self.calendar.get_free_slots(user_id, day=start, minimum_minutes=duration)
            exact_ok = any(start >= s and end <= e for s, e in free_slots)
            if exact_ok:
                return {
                    "can_schedule": True,
                    "summary": title,
                    "start": start,
                    "end": end,
                    "message": f"I found availability at {self._to_ampm(start)}. Shall I add this to your calendar?",
                }

            next_slot = next((slot for slot in free_slots if slot[0] >= now), None)
            if next_slot:
                suggestion_end = next_slot[0] + timedelta(minutes=duration)
                if suggestion_end <= next_slot[1]:
                    return {
                        "can_schedule": True,
                        "summary": title,
                        "start": next_slot[0],
                        "end": suggestion_end,
                        "message": (
                            f"That slot is busy. Next available is {self._to_ampm(next_slot[0])} to "
                            f"{self._to_ampm(suggestion_end)}. Shall I add this to your calendar?"
                        ),
                    }

            return {
                "can_schedule": False,
                "message": "There are no free slots matching that duration today. Want me to look at this week?",
            }

        free_slots, _ = self.calendar.get_free_slots(user_id, minimum_minutes=duration)
        if not free_slots:
            return {
                "can_schedule": False,
                "message": "There are no free slots left today. Want me to check this week or reschedule something?",
            }

        slot = free_slots[0]
        start = slot[0]
        end = start + timedelta(minutes=duration)
        return {
            "can_schedule": True,
            "summary": title,
            "start": start,
            "end": end,
            "message": (
                f"Your next free slot is {self._to_ampm(start)} to {self._to_ampm(end)}. "
                "Shall I add this to your calendar?"
            ),
        }
