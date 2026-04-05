import base64
import hashlib
import hmac
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from google.auth.exceptions import DefaultCredentialsError
from google_auth_oauthlib.flow import Flow

from app.clients.firestore_client import FirestoreClient
from app.clients.calendar_client import CALENDAR_SCOPES
from app.config import get_settings
from app.models import AuthTokenResponse, LoginRequest, SignUpRequest
from app.security import create_access_token, get_current_user_id, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _firestore_client() -> FirestoreClient:
    try:
        return FirestoreClient()
    except DefaultCredentialsError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Google Cloud credentials are not configured for Firestore. "
                "Run 'gcloud auth application-default login' and restart the server."
            ),
        ) from exc


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


def _normalize_email(email: str) -> str:
    value = (email or "").strip().lower()
    if "@" not in value or "." not in value.rsplit("@", maxsplit=1)[-1]:
        raise HTTPException(status_code=400, detail="A valid email is required.")
    return value


def _ensure_jwt_config() -> None:
    settings = get_settings()
    if not settings.jwt_secret:
        raise HTTPException(status_code=500, detail="Server JWT secret is not configured.")


def _ensure_oauth_state_config() -> None:
    settings = get_settings()
    if not settings.state_secret:
        raise HTTPException(status_code=500, detail="Server OAuth state secret is not configured.")


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
def get_auth_url(user_id: str = Depends(get_current_user_id)):
    _ensure_jwt_config()
    _ensure_oauth_state_config()
    settings = get_settings()
    fs = _firestore_client()
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


@router.post("/signup", response_model=AuthTokenResponse)
def signup(payload: SignUpRequest):
    _ensure_jwt_config()
    email = _normalize_email(payload.email)
    password = (payload.password or "").strip()
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    fs = _firestore_client()
    existing = fs.get_user_by_email(email)
    if existing:
        raise HTTPException(status_code=409, detail="User already exists.")

    user_id, user_data = fs.create_user_account(
        email=email,
        password_hash=hash_password(password),
        first_name=payload.first_name,
    )
    token, expires_in = create_access_token(user_id)
    return AuthTokenResponse(
        access_token=token,
        expires_in=expires_in,
        user_id=user_id,
        email=user_data.get("email", email),
    )


@router.post("/login", response_model=AuthTokenResponse)
def login(payload: LoginRequest):
    _ensure_jwt_config()
    email = _normalize_email(payload.email)
    password = (payload.password or "").strip()

    fs = _firestore_client()
    user = fs.get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    user_id, user_data = user
    password_hash = fs.get_user_password_hash(user_id)
    if not password_hash or not verify_password(password, password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token, expires_in = create_access_token(user_id)
    return AuthTokenResponse(
        access_token=token,
        expires_in=expires_in,
        user_id=user_id,
        email=user_data.get("email", email),
    )


@router.get("/me")
def me(user_id: str = Depends(get_current_user_id)):
    _ensure_jwt_config()
    fs = _firestore_client()
    snap = fs.user_ref(user_id).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="User not found.")
    data = snap.to_dict() or {}
    oauth_connected = fs.oauth_ref(user_id).get().exists
    return {
        "user_id": user_id,
        "email": data.get("email", ""),
        "first_name": data.get("firstName", ""),
        "calendar_connected": oauth_connected,
    }


@router.get("/callback")
def oauth_callback(state: str, code: str):
    _ensure_oauth_state_config()
    settings = get_settings()
    fs = _firestore_client()

    parsed_state = _verify_state(state, settings.state_secret)
    user_id = parsed_state.get("user_id")
    issued_at = int(parsed_state.get("ts", 0))
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid state payload")
    now_ts = int(datetime.utcnow().timestamp())
    if issued_at <= 0 or (now_ts - issued_at) > settings.oauth_state_ttl_seconds:
        raise HTTPException(status_code=400, detail="OAuth state has expired")

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
