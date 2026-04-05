from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


Priority = Literal["urgent", "high", "medium", "low"]
TaskTag = Literal["work", "personal", "health", "learning"]
TaskStatus = Literal["pending", "completed"]


class FlowMessageRequest(BaseModel):
    user_id: str
    message: str


class ProposedAction(BaseModel):
    action_type: Literal["calendar.create_event", "task.create", "none"]
    payload: dict[str, Any] = Field(default_factory=dict)


class FlowMessageResponse(BaseModel):
    response: str
    requires_confirmation: bool = False
    proposed_action: ProposedAction = Field(
        default_factory=lambda: ProposedAction(action_type="none", payload={})
    )


class ConfirmActionRequest(BaseModel):
    user_id: str
    action: ProposedAction


class TaskCreate(BaseModel):
    title: str
    due_at: datetime | None = None
    priority: Priority = "medium"
    tag: TaskTag = "work"
    estimated_minutes: int = 60


class TaskUpdate(BaseModel):
    title: str | None = None
    due_at: datetime | None = None
    priority: Priority | None = None
    tag: TaskTag | None = None
    status: TaskStatus | None = None
    estimated_minutes: int | None = None
    calendar_event_id: str | None = None


class TaskOut(BaseModel):
    id: str
    title: str
    due_at: datetime | None = None
    priority: Priority
    tag: TaskTag
    status: TaskStatus
    estimated_minutes: int
    calendar_event_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
