from fastapi import APIRouter, HTTPException

from app.models import TaskCreate, TaskUpdate
from app.services.task_agent import TaskAgent

router = APIRouter(prefix="/users/{user_id}/tasks", tags=["tasks"])


@router.get("")
def list_tasks(user_id: str, status: str | None = None):
    agent = TaskAgent()
    return agent.list_tasks(user_id, status=status)


@router.post("")
def create_task(user_id: str, payload: TaskCreate):
    agent = TaskAgent()
    return agent.create_task(user_id, payload)


@router.patch("/{task_id}")
def update_task(user_id: str, task_id: str, payload: TaskUpdate):
    agent = TaskAgent()
    try:
        return agent.update_task(user_id, task_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{task_id}")
def delete_task(user_id: str, task_id: str):
    agent = TaskAgent()
    try:
        agent.delete_task(user_id, task_id)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
