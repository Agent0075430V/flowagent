from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any


@dataclass
class OtpVerificationResult:
    email: str
    purpose: str
    payload: dict[str, Any]


class OtpStore:
    def __init__(self, file_path: str):
        self._file = Path(file_path)
        self._lock = Lock()
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self._file.exists():
            return {"entries": []}
        try:
            return json.loads(self._file.read_text(encoding="utf-8"))
        except Exception:
            return {"entries": []}

    def _save(self) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def _cleanup_expired(self) -> None:
        now = datetime.now(timezone.utc)
        kept: list[dict[str, Any]] = []
        for item in self._data.get("entries", []):
            expiry_raw = str(item.get("expires_at", ""))
            try:
                expiry = datetime.fromisoformat(expiry_raw)
            except Exception:
                continue
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry > now:
                kept.append(item)
        self._data["entries"] = kept

    def create_otp(self, email: str, purpose: str, payload: dict[str, Any], ttl_seconds: int) -> str:
        code = f"{random.randint(0, 999999):06d}"
        code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=max(60, ttl_seconds))

        with self._lock:
            self._cleanup_expired()
            current = [
                item
                for item in self._data.get("entries", [])
                if not (item.get("email") == email and item.get("purpose") == purpose)
            ]
            current.append(
                {
                    "email": email,
                    "purpose": purpose,
                    "otp_hash": code_hash,
                    "payload": payload,
                    "expires_at": expires_at.isoformat(),
                    "attempts": 0,
                }
            )
            self._data["entries"] = current
            self._save()

        return code

    def verify_otp(self, email: str, purpose: str, otp: str) -> OtpVerificationResult:
        otp_hash = hashlib.sha256((otp or "").strip().encode("utf-8")).hexdigest()

        with self._lock:
            self._cleanup_expired()
            entries = self._data.get("entries", [])
            found_index = -1
            for index, item in enumerate(entries):
                if item.get("email") == email and item.get("purpose") == purpose:
                    found_index = index
                    break

            if found_index < 0:
                raise ValueError("OTP not found or expired.")

            entry = entries[found_index]
            if entry.get("attempts", 0) >= 5:
                entries.pop(found_index)
                self._save()
                raise ValueError("OTP attempts exceeded. Request a new OTP.")

            if entry.get("otp_hash") != otp_hash:
                entry["attempts"] = int(entry.get("attempts", 0)) + 1
                self._save()
                raise ValueError("Invalid OTP.")

            payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
            entries.pop(found_index)
            self._save()

        return OtpVerificationResult(email=email, purpose=purpose, payload=payload)
