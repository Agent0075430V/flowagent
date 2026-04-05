from fastapi import APIRouter, Depends, HTTPException

from app.models import TaskCreate, TaskUpdate
from app.security import get_current_user_id
from app.services.task_agent import TaskAgent

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("")
def list_tasks(status: str | None = None, user_id: str = Depends(get_current_user_id)):
    agent = TaskAgent()
    return agent.list_tasks(user_id, status=status)


@router.post("")
def create_task(payload: TaskCreate, user_id: str = Depends(get_current_user_id)):
    agent = TaskAgent()
    return agent.create_task(user_id, payload)


@router.patch("/{task_id}")
def update_task(task_id: str, payload: TaskUpdate, user_id: str = Depends(get_current_user_id)):
    agent = TaskAgent()
    try:
        return agent.update_task(user_id, task_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{task_id}")
def delete_task(task_id: str, user_id: str = Depends(get_current_user_id)):
    agent = TaskAgent()
    try:
        agent.delete_task(user_id, task_id)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
