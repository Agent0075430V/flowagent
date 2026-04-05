from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.services.calendar_agent import CalendarAgent
from app.services.task_agent import TaskAgent


PRIORITY_RANK = {"urgent": 0, "high": 1, "medium": 2, "low": 3}


class OptimizerAgent:
    def __init__(self) -> None:
        self.calendar = CalendarAgent()
        self.tasks = TaskAgent()

    @staticmethod
    def _is_deep_work(title: str) -> bool:
        t = title.lower()
        return any(k in t for k in ["report", "code", "coding", "write", "slides", "analysis", "design"])

    @staticmethod
    def _is_admin(title: str) -> bool:
        t = title.lower()
        return any(k in t for k in ["email", "review", "admin", "follow up", "cleanup"])

    def optimize_today(self, user_id: str) -> dict:
        free_slots, tz = self.calendar.get_free_slots(user_id, minimum_minutes=30)
        local_tz = ZoneInfo(tz)
        tasks = self.tasks.list_tasks(user_id, status="pending")

        def due_key(task_due: datetime | None) -> float:
            if not task_due:
                return float("inf")
            return task_due.timestamp()

        tasks_sorted = sorted(
            tasks,
            key=lambda t: (PRIORITY_RANK.get(t.priority, 9), due_key(t.due_at)),
        )

        suggestions: list[dict] = []
        used_slots: list[tuple[datetime, datetime]] = []

        for task in tasks_sorted:
            minutes = max(15, task.estimated_minutes)
            preferred_range = None
            if self._is_deep_work(task.title):
                preferred_range = (9, 12)
            elif self._is_admin(task.title):
                preferred_range = (13, 14)
            elif task.tag == "health":
                preferred_range = (12, 13)

            chosen = None
            for slot in free_slots:
                slot_start, slot_end = slot
                if any(not (slot_end <= u[0] or slot_start >= u[1]) for u in used_slots):
                    continue

                if preferred_range:
                    if not (preferred_range[0] <= slot_start.hour < preferred_range[1]):
                        continue

                if (slot_end - slot_start).total_seconds() >= minutes * 60:
                    chosen = (slot_start, slot_start + timedelta(minutes=minutes))
                    break

            if not chosen:
                for slot in free_slots:
                    slot_start, slot_end = slot
                    if any(not (slot_end <= u[0] or slot_start >= u[1]) for u in used_slots):
                        continue
                    if (slot_end - slot_start).total_seconds() >= minutes * 60:
                        chosen = (slot_start, slot_start + timedelta(minutes=minutes))
                        break

            if chosen:
                used_slots.append(chosen)
                suggestions.append(
                    {
                        "title": task.title,
                        "start": chosen[0],
                        "end": chosen[1],
                        "duration": minutes,
                        "taskId": task.id,
                    }
                )

        # Fallback: if nothing fits today, look ahead up to 7 days.
        if not suggestions and tasks_sorted:
            for day_offset in range(1, 8):
                day_anchor = datetime.now(local_tz) + timedelta(days=day_offset)
                day_slots, _ = self.calendar.get_free_slots(user_id, day=day_anchor, minimum_minutes=30)
                if not day_slots:
                    continue

                used_day_slots: list[tuple[datetime, datetime]] = []
                for task in tasks_sorted:
                    minutes = max(15, task.estimated_minutes)

                    chosen = None
                    for slot_start, slot_end in day_slots:
                        if any(not (slot_end <= u[0] or slot_start >= u[1]) for u in used_day_slots):
                            continue
                        if (slot_end - slot_start).total_seconds() >= minutes * 60:
                            chosen = (slot_start, slot_start + timedelta(minutes=minutes))
                            break

                    if chosen:
                        used_day_slots.append(chosen)
                        suggestions.append(
                            {
                                "title": task.title,
                                "start": chosen[0],
                                "end": chosen[1],
                                "duration": minutes,
                                "taskId": task.id,
                            }
                        )

                if suggestions:
                    break

        return {"timezone": tz, "suggestions": suggestions}
