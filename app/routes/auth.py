import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from google.auth.exceptions import DefaultCredentialsError
from google_auth_oauthlib.flow import Flow

from app.clients.firestore_client import FirestoreClient
from app.clients.calendar_client import CALENDAR_SCOPES
from app.config import get_settings
from app.models import (
    AuthTokenResponse,
    ForgotPasswordOtpRequest,
    ForgotPasswordResetRequest,
    LoginRequest,
    SignUpRequest,
    SignupVerifyOtpRequest,
)
from app.services.email_service import EmailService
from app.services.otp_store import OtpStore
from app.security import create_access_token, get_current_user_id, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


@lru_cache
def _otp_store() -> OtpStore:
    return OtpStore(get_settings().otp_store_file)


@lru_cache
def _email_service() -> EmailService:
    return EmailService()


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


def _require_first_name(value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="First name is required.")
    return cleaned


def _password_minimum_or_400(password: str) -> str:
    value = (password or "")
    if len(value.strip()) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")
    return value


def _otp_response_payload(base_message: str, otp: str, email_sent: bool) -> dict:
    settings = get_settings()
    payload = {
        "ok": True,
        "message": base_message,
        "delivery": "email" if email_sent else "dev",
    }
    if not email_sent and settings.otp_dev_echo:
        payload["otp_code"] = otp
        payload["message"] = f"{base_message} (SMTP not configured; dev OTP is returned in response.)"
    return payload


def _ensure_otp_email_delivery(email_sent: bool) -> None:
    if email_sent:
        return
    raise HTTPException(
        status_code=503,
        detail=(
            "OTP email could not be delivered. Configure SMTP settings and try again."
        ),
    )


def _oauth_flow() -> Flow:
    settings = get_settings()
    client_id = (settings.google_client_id or "").strip()
    client_secret = (settings.google_client_secret or "").strip()

    placeholders = (
        "your-google-oauth-client-id",
        "your-google-oauth-client-secret",
        "replace-with",
    )
    invalid_client_id = not client_id or any(token in client_id.lower() for token in placeholders)
    invalid_client_secret = not client_secret or any(token in client_secret.lower() for token in placeholders)

    if invalid_client_id or invalid_client_secret:
        raise HTTPException(
            status_code=500,
            detail=(
                "Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET "
                "with real values from Google Cloud Console OAuth credentials."
            ),
        )

    redirect_uri = (settings.google_redirect_uri or "").strip()
    if not redirect_uri.startswith("http://") and not redirect_uri.startswith("https://"):
        raise HTTPException(status_code=500, detail="GOOGLE_REDIRECT_URI is invalid.")

    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    flow = Flow.from_client_config(client_config, scopes=CALENDAR_SCOPES)
    flow.redirect_uri = redirect_uri
    return flow


@router.get("/url")
def get_auth_url(user_id: str = Depends(get_current_user_id)):
    _ensure_jwt_config()
    _ensure_oauth_state_config()
    settings = get_settings()
    fs = _firestore_client()
    fs.upsert_user_defaults(user_id)

    flow = _oauth_flow()
    state_payload = {"user_id": user_id, "ts": int(datetime.now(timezone.utc).timestamp())}
    signed_state = _sign_state(state_payload, settings.state_secret)

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=signed_state,
    )

    return {"auth_url": auth_url}


@router.post("/signup/request-otp")
def signup_request_otp(payload: SignUpRequest):
    _ensure_jwt_config()
    email = _normalize_email(payload.email)
    first_name = _require_first_name(payload.first_name)
    password = _password_minimum_or_400(payload.password)

    fs = _firestore_client()
    existing = fs.get_user_by_email(email)
    if existing:
        raise HTTPException(status_code=409, detail="User already exists.")

    otp = _otp_store().create_otp(
        email=email,
        purpose="signup",
        payload={
            "first_name": first_name,
            "password_hash": hash_password(password),
        },
        ttl_seconds=get_settings().otp_ttl_seconds,
    )

    email_sent = False
    try:
        email_sent = _email_service().send_otp_email(email, otp, purpose="signup")
    except Exception:
        logger.exception("Failed to send signup OTP email")

    _ensure_otp_email_delivery(email_sent)

    return _otp_response_payload("OTP sent for signup verification.", otp, email_sent)


@router.post("/signup/verify-otp", response_model=AuthTokenResponse)
def signup_verify_otp(payload: SignupVerifyOtpRequest):
    _ensure_jwt_config()
    email = _normalize_email(payload.email)
    otp = (payload.otp or "").strip()
    if len(otp) != 6 or not otp.isdigit():
        raise HTTPException(status_code=400, detail="A valid 6-digit OTP is required.")

    fs = _firestore_client()
    existing = fs.get_user_by_email(email)
    if existing:
        raise HTTPException(status_code=409, detail="User already exists.")

    try:
        verified = _otp_store().verify_otp(email=email, purpose="signup", otp=otp)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    first_name = _require_first_name(str(verified.payload.get("first_name", "")))
    password_hash = str(verified.payload.get("password_hash", "")).strip()
    if not password_hash:
        raise HTTPException(status_code=400, detail="Signup session invalid. Please request OTP again.")

    user_id, user_data = fs.create_user_account(
        email=email,
        password_hash=password_hash,
        first_name=first_name,
    )
    token, expires_in = create_access_token(user_id)
    return AuthTokenResponse(
        access_token=token,
        expires_in=expires_in,
        user_id=user_id,
        email=user_data.get("email", email),
    )


@router.post("/signup", response_model=AuthTokenResponse)
def signup(payload: SignUpRequest):
    raise HTTPException(
        status_code=400,
        detail="Signup now requires OTP verification. Use /auth/signup/request-otp and /auth/signup/verify-otp.",
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


@router.post("/password/forgot/request-otp")
def forgot_password_request_otp(payload: ForgotPasswordOtpRequest):
    email = _normalize_email(payload.email)
    fs = _firestore_client()
    user = fs.get_user_by_email(email)
    if not user:
        return {"ok": True, "message": "If the email exists, an OTP has been sent."}

    user_id, _ = user
    otp = _otp_store().create_otp(
        email=email,
        purpose="password_reset",
        payload={"user_id": user_id},
        ttl_seconds=get_settings().otp_ttl_seconds,
    )

    email_sent = False
    try:
        email_sent = _email_service().send_otp_email(email, otp, purpose="password_reset")
    except Exception:
        logger.exception("Failed to send password-reset OTP email")

    _ensure_otp_email_delivery(email_sent)

    return _otp_response_payload("OTP sent for password reset.", otp, email_sent)


@router.post("/password/forgot/verify-otp")
def forgot_password_verify_otp(payload: ForgotPasswordResetRequest):
    email = _normalize_email(payload.email)
    otp = (payload.otp or "").strip()
    new_password = _password_minimum_or_400(payload.new_password)

    if len(otp) != 6 or not otp.isdigit():
        raise HTTPException(status_code=400, detail="A valid 6-digit OTP is required.")

    try:
        verified = _otp_store().verify_otp(email=email, purpose="password_reset", otp=otp)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user_id = str(verified.payload.get("user_id", "")).strip()
    fs = _firestore_client()
    if not user_id:
        existing = fs.get_user_by_email(email)
        if not existing:
            raise HTTPException(status_code=404, detail="User not found.")
        user_id, _ = existing

    fs.update_user_password_hash(user_id, hash_password(new_password))
    return {"ok": True, "message": "Password reset successful."}


@router.get("/me")
def me(user_id: str = Depends(get_current_user_id)):
    _ensure_jwt_config()
    fs = _firestore_client()
    snap = fs.user_ref(user_id).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="User not found.")
    data = snap.to_dict() or {}
    oauth_connected = True
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
    now_ts = int(datetime.now(timezone.utc).timestamp())
    if issued_at <= 0 or (now_ts - issued_at) > settings.oauth_state_ttl_seconds:
        raise HTTPException(status_code=400, detail="OAuth state has expired")

    flow = _oauth_flow()
    flow.fetch_token(code=code)
    creds = flow.credentials

    oauth_snap = fs.oauth_ref(user_id).get()
    existing = oauth_snap.to_dict() if oauth_snap.exists else {}
    refresh_token = creds.refresh_token or existing.get("refresh_token")

    token_payload = {
        "access_token": creds.token,
        "refresh_token": refresh_token,
        "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": CALENDAR_SCOPES,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "updatedAt": datetime.now(timezone.utc),
    }
    fs.oauth_ref(user_id).set(token_payload, merge=True)

    return {"ok": True, "message": "Google Calendar connected successfully.", "user_id": user_id}
