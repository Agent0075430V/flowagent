from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.clients.firestore_client import FirestoreClient


class CalendarAgent:
    def __init__(self) -> None:
        self.fs = FirestoreClient()

    def _user_context(self, user_id: str) -> tuple[dict, dict]:
        user = self.fs.upsert_user_defaults(user_id)
        return user, {}

    @staticmethod
    def _to_local_dt(value, tz: str) -> datetime | None:
        if value is None:
            return None
        local_tz = ZoneInfo(tz)
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=local_tz)
            return value.astimezone(local_tz)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=local_tz)
            return parsed.astimezone(local_tz)
        return None

    def _local_events_between(self, user_id: str, tz: str, start: datetime, end: datetime) -> list[dict]:
        events: list[dict] = []
        for doc in self.fs.task_collection(user_id).stream():
            data = doc.to_dict() or {}
            due_at = self._to_local_dt(data.get("dueAt"), tz)
            if not due_at:
                continue
            duration = max(15, int(data.get("estimatedMinutes", 60) or 60))
            event_end = due_at + timedelta(minutes=duration)
            if event_end <= start or due_at >= end:
                continue
            events.append(
                {
                    "id": data.get("calendarEventId") or f"local-{doc.id}",
                    "summary": data.get("title", "Task"),
                    "start": due_at,
                    "end": event_end,
                }
            )
        events.sort(key=lambda item: item["start"])
        return events

    def _save_refreshed_token(self, user_id: str, token_payload: dict) -> None:
        _ = (user_id, token_payload)

    def get_today_events(self, user_id: str) -> tuple[list[dict], str]:
        user, _ = self._user_context(user_id)
        tz = user.get("timezone", "Asia/Kolkata")
        now = datetime.now(ZoneInfo(tz))
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        events = self._local_events_between(user_id, tz, day_start, day_end)
        return events, tz

    def get_week_events(self, user_id: str) -> tuple[list[dict], str]:
        user, _ = self._user_context(user_id)
        tz = user.get("timezone", "Asia/Kolkata")
        start = datetime.now(ZoneInfo(tz))
        end = start + timedelta(days=7)
        events = self._local_events_between(user_id, tz, start, end)
        return events, tz

    def create_event(self, user_id: str, summary: str, start: datetime, end: datetime, description: str = "") -> dict:
        _ = description
        tz = self.fs.upsert_user_defaults(user_id).get("timezone", "Asia/Kolkata")
        start_local = start.astimezone(ZoneInfo(tz)) if start.tzinfo else start.replace(tzinfo=ZoneInfo(tz))
        end_local = end.astimezone(ZoneInfo(tz)) if end.tzinfo else end.replace(tzinfo=ZoneInfo(tz))
        minutes = max(15, int((end_local - start_local).total_seconds() // 60))
        doc_ref = self.fs.task_collection(user_id).document()
        now = datetime.now(ZoneInfo(tz))
        event_id = f"local-{doc_ref.id}"
        doc_ref.set(
            {
                "title": summary,
                "dueAt": start_local,
                "priority": "medium",
                "tag": "work",
                "status": "pending",
                "estimatedMinutes": minutes,
                "calendarEventId": event_id,
                "createdAt": now,
                "updatedAt": now,
            }
        )
        return {"id": event_id, "summary": summary, "start": start_local.isoformat(), "end": end_local.isoformat()}

    def get_free_slots(
        self,
        user_id: str,
        day: datetime | None = None,
        minimum_minutes: int = 30,
    ) -> tuple[list[tuple[datetime, datetime]], str]:
        user, _ = self._user_context(user_id)
        tz = user.get("timezone", "Asia/Kolkata")
        work_start_str = user.get("workStart", "09:00")
        work_end_str = user.get("workEnd", "19:00")

        local_tz = ZoneInfo(tz)
        anchor = day.astimezone(local_tz) if day else datetime.now(local_tz)
        day_start = anchor.replace(hour=0, minute=0, second=0, microsecond=0)
        events = self._local_events_between(user_id, tz, day_start, day_start + timedelta(days=1))

        wh_start_hour, wh_start_minute = map(int, work_start_str.split(":"))
        wh_end_hour, wh_end_minute = map(int, work_end_str.split(":"))

        window_start = day_start.replace(hour=wh_start_hour, minute=wh_start_minute)
        window_end = day_start.replace(hour=wh_end_hour, minute=wh_end_minute)

        busy: list[tuple[datetime, datetime]] = []
        for event in events:
            st_local = event["start"].astimezone(local_tz)
            en_local = event["end"].astimezone(local_tz)
            busy.append((st_local - timedelta(minutes=15), en_local + timedelta(minutes=15)))

        busy.sort(key=lambda x: x[0])
        merged: list[tuple[datetime, datetime]] = []
        for interval in busy:
            if not merged or interval[0] > merged[-1][1]:
                merged.append(interval)
            else:
                merged[-1] = (merged[-1][0], max(merged[-1][1], interval[1]))

        free: list[tuple[datetime, datetime]] = []
        cursor = window_start
        for start, end in merged:
            if end <= window_start or start >= window_end:
                continue
            clipped_start = max(start, window_start)
            clipped_end = min(end, window_end)
            if clipped_start > cursor and (clipped_start - cursor).total_seconds() >= minimum_minutes * 60:
                free.append((cursor, clipped_start))
            cursor = max(cursor, clipped_end)

        if cursor < window_end and (window_end - cursor).total_seconds() >= minimum_minutes * 60:
            free.append((cursor, window_end))

        return free, tz
