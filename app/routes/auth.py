import base64
import hashlib
import hmac
import json
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request
from google_auth_oauthlib.flow import Flow

from app.clients.firestore_client import FirestoreClient
from app.clients.calendar_client import CALENDAR_SCOPES
from app.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


def _sign_state(payload: dict, secret: str) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    b64 = base64.urlsafe_b64encode(raw).decode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


def _verify_state(state: str, secret: str) -> dict:
    try:
        b64, sig = state.split(".", maxsplit=1)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid state format") from exc

    expected = hmac.new(secret.encode("utf-8"), b64.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=400, detail="Invalid state signature")

    raw = base64.urlsafe_b64decode(b64.encode("utf-8"))
    return json.loads(raw.decode("utf-8"))


def _oauth_flow() -> Flow:
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=500, detail="Missing Google OAuth credentials")

    client_config = {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }
    flow = Flow.from_client_config(client_config, scopes=CALENDAR_SCOPES)
    flow.redirect_uri = settings.google_redirect_uri
    return flow


@router.get("/url")
def get_auth_url(user_id: str = Query(..., min_length=3)):
    settings = get_settings()
    fs = FirestoreClient()
    fs.upsert_user_defaults(user_id)

    flow = _oauth_flow()
    state_payload = {"user_id": user_id, "ts": int(datetime.utcnow().timestamp())}
    signed_state = _sign_state(state_payload, settings.state_secret)

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=signed_state,
    )

    return {"auth_url": auth_url}


@router.get("/callback")
def oauth_callback(request: Request, state: str, code: str):
    settings = get_settings()
    fs = FirestoreClient()

    parsed_state = _verify_state(state, settings.state_secret)
    user_id = parsed_state.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid state payload")

    flow = _oauth_flow()
    flow.fetch_token(code=code)
    creds = flow.credentials

    existing = fs.oauth_ref(user_id).get().to_dict() if fs.oauth_ref(user_id).get().exists else {}
    refresh_token = creds.refresh_token or existing.get("refresh_token")

    token_payload = {
        "access_token": creds.token,
        "refresh_token": refresh_token,
        "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": CALENDAR_SCOPES,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "updatedAt": datetime.utcnow(),
    }
    fs.oauth_ref(user_id).set(token_payload, merge=True)

    return {"ok": True, "message": "Google Calendar connected successfully.", "user_id": user_id}
