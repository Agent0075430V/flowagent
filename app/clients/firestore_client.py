from datetime import datetime
from google.cloud import firestore
from app.config import get_settings


class FirestoreClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.db = firestore.Client(project=settings.gcp_project_id, database=settings.firestore_database)

    def user_ref(self, user_id: str):
        return self.db.collection("users").document(user_id)

    def task_collection(self, user_id: str):
        return self.user_ref(user_id).collection("tasks")

    def oauth_ref(self, user_id: str):
        return self.user_ref(user_id).collection("oauth").document("google")

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
