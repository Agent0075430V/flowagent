from fastapi import APIRouter, HTTPException

from app.models import ConfirmActionRequest, FlowMessageRequest
from app.services.flow_service import FlowService

router = APIRouter(prefix="/flow", tags=["flow"])


@router.post("/message")
def handle_message(payload: FlowMessageRequest):
    try:
        service = FlowService()
        return service.handle_message(payload.user_id, payload.message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/confirm")
def confirm_action(payload: ConfirmActionRequest):
    try:
        service = FlowService()
        message = service.confirm_action(
            user_id=payload.user_id,
            action_type=payload.action.action_type,
            payload=payload.action.payload,
        )
        return {"ok": True, "message": message}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
