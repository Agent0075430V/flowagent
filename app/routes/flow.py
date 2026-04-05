from fastapi import APIRouter, Depends, HTTPException

from app.models import ConfirmActionRequest, FlowMessageRequest
from app.security import get_current_user_id
from app.services.flow_service import FlowService

router = APIRouter(prefix="/flow", tags=["flow"])


@router.post("/message")
def handle_message(payload: FlowMessageRequest, user_id: str = Depends(get_current_user_id)):
    try:
        service = FlowService()
        return service.handle_message(user_id, payload.message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/confirm")
def confirm_action(payload: ConfirmActionRequest, user_id: str = Depends(get_current_user_id)):
    try:
        service = FlowService()
        message = service.confirm_action(
            user_id=user_id,
            action_type=payload.action.action_type,
            payload=payload.action.payload,
        )
        return {"ok": True, "message": message}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
