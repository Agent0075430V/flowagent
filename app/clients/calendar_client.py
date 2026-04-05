from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError
from googleapiclient.discovery import build
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]


class CalendarClient:
    @staticmethod
    def _service(token_payload: dict):
        creds = Credentials(
            token=token_payload.get("access_token"),
            refresh_token=token_payload.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=token_payload.get("client_id"),
            client_secret=token_payload.get("client_secret"),
            scopes=CALENDAR_SCOPES,
        )

        if not creds.valid:
            if not creds.refresh_token:
                raise ValueError("Calendar authorization expired. Reconnect Google Calendar.")
            try:
                creds.refresh(Request())
                token_payload["access_token"] = creds.token
                token_payload["expiry"] = creds.expiry.isoformat() if creds.expiry else None
            except RefreshError as exc:
                raise ValueError("Google token refresh failed. Reconnect Google Calendar.") from exc

        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((HttpError, TimeoutError, ConnectionError)),
    )
    def list_events(self, token_payload: dict, tz: str, start: datetime, end: datetime) -> list[dict]:
        service = self._service(token_payload)
        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=start.astimezone(ZoneInfo("UTC")).isoformat(),
                timeMax=end.astimezone(ZoneInfo("UTC")).isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=250,
            )
            .execute()
        )
        return events_result.get("items", [])

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((HttpError, TimeoutError, ConnectionError)),
    )
    def create_event(self, token_payload: dict, summary: str, start: datetime, end: datetime, tz: str, description: str = "") -> dict:
        service = self._service(token_payload)
        event_body = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start.isoformat(), "timeZone": tz},
            "end": {"dateTime": end.isoformat(), "timeZone": tz},
        }
        return service.events().insert(calendarId="primary", body=event_body).execute()

    @staticmethod
    def parse_event_time(event: dict, tz: str) -> tuple[datetime, datetime]:
        start_info = event.get("start", {})
        end_info = event.get("end", {})

        if "dateTime" in start_info:
            start_dt = datetime.fromisoformat(start_info["dateTime"].replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_info["dateTime"].replace("Z", "+00:00"))
        else:
            local_tz = ZoneInfo(tz)
            start_dt = datetime.fromisoformat(start_info["date"]).replace(tzinfo=local_tz)
            end_dt = datetime.fromisoformat(end_info["date"]).replace(tzinfo=local_tz)

        return start_dt, end_dt

    @staticmethod
    def now_in_tz(tz: str) -> datetime:
        return datetime.now(ZoneInfo(tz))

    @staticmethod
    def week_window(tz: str) -> tuple[datetime, datetime]:
        now = datetime.now(ZoneInfo(tz))
        end = now + timedelta(days=7)
        return now, end
