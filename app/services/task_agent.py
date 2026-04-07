from datetime import datetime, timezone
from google.cloud.firestore_v1.base_query import FieldFilter

from app.clients.firestore_client import FirestoreClient
from app.models import TaskCreate, TaskOut, TaskUpdate


class TaskAgent:
    def __init__(self) -> None:
        self.fs = FirestoreClient()

    def list_tasks(self, user_id: str, status: str | None = None) -> list[TaskOut]:
        self.fs.upsert_user_defaults(user_id)
        query = self.fs.task_collection(user_id)
        if status:
            query = query.where(filter=FieldFilter("status", "==", status))

        docs = query.stream()
        result: list[TaskOut] = []
        for doc in docs:
            data = doc.to_dict() or {}
            result.append(
                TaskOut(
                    id=doc.id,
                    title=data.get("title", ""),
                    due_at=data.get("dueAt"),
                    priority=data.get("priority", "medium"),
                    tag=data.get("tag", "work"),
                    status=data.get("status", "pending"),
                    estimated_minutes=data.get("estimatedMinutes", 60),
                    calendar_event_id=data.get("calendarEventId"),
                    created_at=data.get("createdAt"),
                    updated_at=data.get("updatedAt"),
                )
            )
        result.sort(key=lambda t: (t.status, t.priority, t.due_at or datetime.max.replace(tzinfo=timezone.utc)))
        return result

    def create_task(self, user_id: str, payload: TaskCreate) -> TaskOut:
        self.fs.upsert_user_defaults(user_id)
        now = datetime.now(timezone.utc)
        doc_data = {
            "title": payload.title,
            "dueAt": payload.due_at,
            "priority": payload.priority,
            "tag": payload.tag,
            "status": "pending",
            "estimatedMinutes": payload.estimated_minutes,
            "calendarEventId": None,
            "createdAt": now,
            "updatedAt": now,
        }
        ref = self.fs.task_collection(user_id).document()
        ref.set(doc_data)
        return TaskOut(
            id=ref.id,
            title=payload.title,
            due_at=payload.due_at,
            priority=payload.priority,
            tag=payload.tag,
            status="pending",
            estimated_minutes=payload.estimated_minutes,
            calendar_event_id=None,
            created_at=now,
            updated_at=now,
        )

    def update_task(self, user_id: str, task_id: str, payload: TaskUpdate) -> TaskOut:
        self.fs.upsert_user_defaults(user_id)
        ref = self.fs.task_collection(user_id).document(task_id)
        snap = ref.get()
        if not snap.exists:
            raise ValueError("Task not found")

        patch: dict = {}
        mapping = {
            "title": payload.title,
            "dueAt": payload.due_at,
            "priority": payload.priority,
            "tag": payload.tag,
            "status": payload.status,
            "estimatedMinutes": payload.estimated_minutes,
            "calendarEventId": payload.calendar_event_id,
        }
        for key, value in mapping.items():
            if value is not None:
                patch[key] = value
        patch["updatedAt"] = datetime.now(timezone.utc)

        ref.set(patch, merge=True)
        merged = snap.to_dict() or {}
        merged.update(patch)
        return TaskOut(
            id=task_id,
            title=merged.get("title", ""),
            due_at=merged.get("dueAt"),
            priority=merged.get("priority", "medium"),
            tag=merged.get("tag", "work"),
            status=merged.get("status", "pending"),
            estimated_minutes=merged.get("estimatedMinutes", 60),
            calendar_event_id=merged.get("calendarEventId"),
            created_at=merged.get("createdAt"),
            updated_at=merged.get("updatedAt"),
        )

    def delete_task(self, user_id: str, task_id: str) -> None:
        self.fs.upsert_user_defaults(user_id)
        ref = self.fs.task_collection(user_id).document(task_id)
        if not ref.get().exists:
            raise ValueError("Task not found")
        ref.delete()
