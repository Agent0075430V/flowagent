from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4

from google.auth.exceptions import DefaultCredentialsError
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from app.config import get_settings


class _LocalSnapshot:
    def __init__(self, data: dict | None):
        self._data = deepcopy(data) if isinstance(data, dict) else None
        self.exists = self._data is not None

    def to_dict(self) -> dict:
        return deepcopy(self._data) if self._data is not None else {}


class _LocalQuery:
    def __init__(self, docs: list[tuple[str, dict]], field: str | None = None, op: str | None = None, value=None):
        self._docs = docs
        self._field = field
        self._op = op or "=="
        self._value = value
        self._limit: int | None = None

    def where(self, filter: FieldFilter | None = None):
        field = getattr(filter, "field_path", None)
        op = getattr(filter, "op_string", None)
        value = getattr(filter, "value", None)
        query = _LocalQuery(self._docs, field=field, op=op, value=value)
        query._limit = self._limit
        return query

    def limit(self, count: int):
        self._limit = count
        return self

    def _match(self, data: dict) -> bool:
        if not self._field:
            return True
        if self._op != "==":
            return False
        return data.get(self._field) == self._value

    def stream(self):
        rows = [
            _LocalTaskDoc(doc_id, payload)
            for doc_id, payload in self._docs
            if self._match(payload)
        ]
        if self._limit is not None:
            rows = rows[: self._limit]
        return rows


class _LocalTaskDoc:
    def __init__(self, doc_id: str, payload: dict):
        self.id = doc_id
        self._payload = deepcopy(payload)

    def to_dict(self):
        return deepcopy(self._payload)


class _LocalTaskDocRef:
    def __init__(self, store: "_LocalStore", user_id: str, task_id: str):
        self._store = store
        self._user_id = user_id
        self.id = task_id

    def get(self):
        return _LocalSnapshot(self._store.get_task(self._user_id, self.id))

    def set(self, payload: dict, merge: bool = False):
        self._store.set_task(self._user_id, self.id, payload, merge=merge)

    def delete(self):
        self._store.delete_task(self._user_id, self.id)


class _LocalTaskCollection:
    def __init__(self, store: "_LocalStore", user_id: str):
        self._store = store
        self._user_id = user_id

    def document(self, task_id: str | None = None):
        return _LocalTaskDocRef(self._store, self._user_id, task_id or uuid4().hex)

    def where(self, filter: FieldFilter | None = None):
        docs = list(self._store.list_task_docs(self._user_id))
        return _LocalQuery(docs).where(filter=filter)

    def stream(self):
        return [_LocalTaskDoc(doc_id, payload) for doc_id, payload in self._store.list_task_docs(self._user_id)]


class _LocalSubDocRef:
    def __init__(self, store: "_LocalStore", user_id: str, kind: str):
        self._store = store
        self._user_id = user_id
        self._kind = kind

    def get(self):
        if self._kind == "oauth":
            return _LocalSnapshot(self._store.get_oauth(self._user_id))
        if self._kind == "auth":
            return _LocalSnapshot(self._store.get_auth(self._user_id))
        return _LocalSnapshot(None)

    def set(self, payload: dict, merge: bool = False):
        if self._kind == "oauth":
            self._store.set_oauth(self._user_id, payload, merge=merge)
        if self._kind == "auth":
            self._store.set_auth(self._user_id, payload, merge=merge)


class _LocalSubCollection:
    def __init__(self, store: "_LocalStore", user_id: str, kind: str):
        self._store = store
        self._user_id = user_id
        self._kind = kind

    def document(self, _name: str):
        return _LocalSubDocRef(self._store, self._user_id, self._kind)


class _LocalUserDocRef:
    def __init__(self, store: "_LocalStore", user_id: str):
        self._store = store
        self.id = user_id

    def get(self):
        return _LocalSnapshot(self._store.get_user(self.id))

    def set(self, payload: dict, merge: bool = False):
        self._store.set_user(self.id, payload, merge=merge)

    def collection(self, name: str):
        if name == "tasks":
            return _LocalTaskCollection(self._store, self.id)
        if name == "oauth":
            return _LocalSubCollection(self._store, self.id, "oauth")
        if name == "auth":
            return _LocalSubCollection(self._store, self.id, "auth")
        raise ValueError(f"Unsupported local collection: {name}")


class _LocalUserCollection:
    def __init__(self, store: "_LocalStore"):
        self._store = store

    def document(self, user_id: str | None = None):
        return _LocalUserDocRef(self._store, user_id or uuid4().hex)

    def where(self, filter: FieldFilter | None = None):
        docs = list(self._store.list_users())
        return _LocalQuery(docs).where(filter=filter)


class _LocalStore:
    def __init__(self, file_path: str):
        self._file = Path(file_path)
        self._lock = Lock()
        self._data = self._load()

    def _load(self) -> dict:
        if not self._file.exists():
            return {"users": {}}
        try:
            import json

            return json.loads(self._file.read_text(encoding="utf-8"))
        except Exception:
            return {"users": {}}

    def _save(self):
        import json

        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(json.dumps(self._data, default=str, indent=2), encoding="utf-8")

    def _ensure_user(self, user_id: str):
        users = self._data.setdefault("users", {})
        user = users.setdefault(user_id, {})
        user.setdefault("tasks", {})
        user.setdefault("oauth", {})
        user.setdefault("auth", {})
        return user

    def get_user(self, user_id: str) -> dict | None:
        users = self._data.get("users", {})
        if user_id not in users:
            return None
        user = deepcopy(users[user_id])
        user.pop("tasks", None)
        user.pop("oauth", None)
        user.pop("auth", None)
        return user

    def set_user(self, user_id: str, payload: dict, merge: bool = False):
        with self._lock:
            user = self._ensure_user(user_id)
            if merge:
                for key, value in payload.items():
                    if key in {"tasks", "oauth", "auth"}:
                        continue
                    user[key] = value
            else:
                tasks = user.get("tasks", {})
                oauth = user.get("oauth", {})
                auth = user.get("auth", {})
                user.clear()
                user.update({k: v for k, v in payload.items() if k not in {"tasks", "oauth", "auth"}})
                user["tasks"] = tasks
                user["oauth"] = oauth
                user["auth"] = auth
            self._save()

    def list_users(self):
        for user_id, data in self._data.get("users", {}).items():
            payload = deepcopy(data)
            payload.pop("tasks", None)
            payload.pop("oauth", None)
            payload.pop("auth", None)
            yield user_id, payload

    def get_auth(self, user_id: str) -> dict | None:
        user = self._data.get("users", {}).get(user_id)
        if not user:
            return None
        data = user.get("auth", {}).get("credentials")
        return deepcopy(data) if isinstance(data, dict) else None

    def set_auth(self, user_id: str, payload: dict, merge: bool = False):
        with self._lock:
            user = self._ensure_user(user_id)
            current = user.setdefault("auth", {}).setdefault("credentials", {})
            if merge:
                current.update(payload)
            else:
                user["auth"]["credentials"] = deepcopy(payload)
            self._save()

    def get_oauth(self, user_id: str) -> dict | None:
        user = self._data.get("users", {}).get(user_id)
        if not user:
            return None
        data = user.get("oauth", {}).get("google")
        return deepcopy(data) if isinstance(data, dict) else None

    def set_oauth(self, user_id: str, payload: dict, merge: bool = False):
        with self._lock:
            user = self._ensure_user(user_id)
            current = user.setdefault("oauth", {}).setdefault("google", {})
            if merge:
                current.update(payload)
            else:
                user["oauth"]["google"] = deepcopy(payload)
            self._save()

    def list_task_docs(self, user_id: str):
        user = self._data.get("users", {}).get(user_id, {})
        for task_id, payload in user.get("tasks", {}).items():
            yield task_id, deepcopy(payload)

    def get_task(self, user_id: str, task_id: str) -> dict | None:
        user = self._data.get("users", {}).get(user_id, {})
        task = user.get("tasks", {}).get(task_id)
        return deepcopy(task) if isinstance(task, dict) else None

    def set_task(self, user_id: str, task_id: str, payload: dict, merge: bool = False):
        with self._lock:
            user = self._ensure_user(user_id)
            tasks = user.setdefault("tasks", {})
            if merge and isinstance(tasks.get(task_id), dict):
                tasks[task_id].update(payload)
            else:
                tasks[task_id] = deepcopy(payload)
            self._save()

    def delete_task(self, user_id: str, task_id: str):
        with self._lock:
            user = self._ensure_user(user_id)
            user.setdefault("tasks", {}).pop(task_id, None)
            self._save()


class FirestoreClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.is_local = False
        self.local_reason: str | None = None
        self._local_store: _LocalStore | None = None

        try:
            self.db = firestore.Client(project=settings.gcp_project_id, database=settings.firestore_database)
        except DefaultCredentialsError:
            if not settings.enable_local_fallback_store:
                raise
            self.is_local = True
            self.local_reason = "missing-google-credentials"
            self._local_store = _LocalStore(settings.local_fallback_store_file)
            self.db = None

    def user_ref(self, user_id: str):
        if self.is_local and self._local_store:
            return _LocalUserDocRef(self._local_store, user_id)
        return self.db.collection("users").document(user_id)

    def task_collection(self, user_id: str):
        return self.user_ref(user_id).collection("tasks")

    def oauth_ref(self, user_id: str):
        return self.user_ref(user_id).collection("oauth").document("google")

    def user_auth_ref(self, user_id: str):
        return self.user_ref(user_id).collection("auth").document("credentials")

    def get_user_by_email(self, email: str) -> tuple[str, dict] | None:
        normalized = email.lower().strip()
        if self.is_local and self._local_store:
            for user_id, payload in self._local_store.list_users():
                if payload.get("email") == normalized:
                    return user_id, payload
            return None

        query = (
            self.db.collection("users")
            .where(filter=FieldFilter("email", "==", normalized))
            .limit(1)
        )
        docs = list(query.stream())
        if not docs:
            return None

        doc = docs[0]
        return doc.id, (doc.to_dict() or {})

    def create_user_account(self, email: str, password_hash: str, first_name: str = "") -> tuple[str, dict]:
        now = datetime.utcnow()
        doc_ref = self.user_ref(uuid4().hex if self.is_local else None)
        user_payload = {
            "email": email.lower().strip(),
            "firstName": first_name.strip(),
            "timezone": get_settings().default_timezone,
            "workStart": get_settings().default_work_start,
            "workEnd": get_settings().default_work_end,
            "createdAt": now,
            "updatedAt": now,
        }
        doc_ref.set(user_payload)
        self.user_auth_ref(doc_ref.id).set(
            {
                "passwordHash": password_hash,
                "createdAt": now,
                "updatedAt": now,
            }
        )
        return doc_ref.id, user_payload

    def get_user_password_hash(self, user_id: str) -> str | None:
        snap = self.user_auth_ref(user_id).get()
        if not snap.exists:
            return None
        data = snap.to_dict() or {}
        return data.get("passwordHash")

    def upsert_user_defaults(self, user_id: str) -> dict:
        settings = get_settings()
        doc_ref = self.user_ref(user_id)
        snap = doc_ref.get()
        if not snap.exists:
            payload = {
                "firstName": "",
                "timezone": settings.default_timezone,
                "workStart": settings.default_work_start,
                "workEnd": settings.default_work_end,
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow(),
            }
            doc_ref.set(payload)
            return payload

        data = snap.to_dict() or {}
        patch = {}
        if "timezone" not in data:
            patch["timezone"] = settings.default_timezone
        if "workStart" not in data:
            patch["workStart"] = settings.default_work_start
        if "workEnd" not in data:
            patch["workEnd"] = settings.default_work_end
        if patch:
            patch["updatedAt"] = datetime.utcnow()
            doc_ref.set(patch, merge=True)
            data.update(patch)
        return data
