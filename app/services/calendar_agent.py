from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.clients.calendar_client import CalendarClient
from app.clients.firestore_client import FirestoreClient


class CalendarAgent:
    def __init__(self) -> None:
        self.fs = FirestoreClient()
        self.calendar = CalendarClient()

    def _user_context(self, user_id: str) -> tuple[dict, dict]:
        user = self.fs.upsert_user_defaults(user_id)
        oauth_snap = self.fs.oauth_ref(user_id).get()
        if not oauth_snap.exists:
            raise ValueError("Google Calendar is not connected. Complete OAuth first.")
        token_payload = oauth_snap.to_dict() or {}
        return user, token_payload

    def get_today_events(self, user_id: str) -> tuple[list[dict], str]:
        user, token_payload = self._user_context(user_id)
        tz = user.get("timezone", "Asia/Kolkata")
        now = datetime.now(ZoneInfo(tz))
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        events = self.calendar.list_events(token_payload, tz, day_start, day_end)
        return events, tz

    def get_week_events(self, user_id: str) -> tuple[list[dict], str]:
        user, token_payload = self._user_context(user_id)
        tz = user.get("timezone", "Asia/Kolkata")
        start = datetime.now(ZoneInfo(tz))
        end = start + timedelta(days=7)
        events = self.calendar.list_events(token_payload, tz, start, end)
        return events, tz

    def create_event(self, user_id: str, summary: str, start: datetime, end: datetime, description: str = "") -> dict:
        user, token_payload = self._user_context(user_id)
        tz = user.get("timezone", "Asia/Kolkata")
        return self.calendar.create_event(token_payload, summary, start, end, tz, description)

    def get_free_slots(
        self,
        user_id: str,
        day: datetime | None = None,
        minimum_minutes: int = 30,
    ) -> tuple[list[tuple[datetime, datetime]], str]:
        user, token_payload = self._user_context(user_id)
        tz = user.get("timezone", "Asia/Kolkata")
        work_start_str = user.get("workStart", "09:00")
        work_end_str = user.get("workEnd", "19:00")

        local_tz = ZoneInfo(tz)
        anchor = day.astimezone(local_tz) if day else datetime.now(local_tz)
        day_start = anchor.replace(hour=0, minute=0, second=0, microsecond=0)
        events = self.calendar.list_events(token_payload, tz, day_start, day_start + timedelta(days=1))

        wh_start_hour, wh_start_minute = map(int, work_start_str.split(":"))
        wh_end_hour, wh_end_minute = map(int, work_end_str.split(":"))

        window_start = day_start.replace(hour=wh_start_hour, minute=wh_start_minute)
        window_end = day_start.replace(hour=wh_end_hour, minute=wh_end_minute)

        busy: list[tuple[datetime, datetime]] = []
        for event in events:
            st, en = self.calendar.parse_event_time(event, tz)
            st_local = st.astimezone(local_tz)
            en_local = en.astimezone(local_tz)
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
