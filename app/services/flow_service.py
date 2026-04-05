from datetime import datetime

from app.models import FlowMessageResponse, ProposedAction, TaskCreate, TaskUpdate
from app.services.calendar_agent import CalendarAgent
from app.services.intent_classifier import classify_intent
from app.services.optimizer_agent import OptimizerAgent
from app.services.scheduling_agent import SchedulingAgent
from app.services.task_agent import TaskAgent


class FlowService:
    def __init__(self) -> None:
        self.calendar = CalendarAgent()
        self.tasks = TaskAgent()
        self.optimizer = OptimizerAgent()
        self.scheduler = SchedulingAgent()

    @staticmethod
    def _fmt(dt: datetime) -> str:
        return dt.strftime("%I:%M %p").lstrip("0")

    def handle_message(self, user_id: str, message: str) -> FlowMessageResponse:
        intent = classify_intent(message)

        if intent == "free_time":
            free, _ = self.calendar.get_free_slots(user_id)
            if not free:
                return FlowMessageResponse(
                    response="You have no free slots left today. Want me to check this week or reschedule something?"
                )

            windows = [f"{self._fmt(s)} to {self._fmt(e)}" for s, e in free[:3]]
            joined = ", ".join(windows)
            return FlowMessageResponse(response=f"You are free during: {joined}. Want me to block one for a task?")

        if intent == "task":
            if message.lower().startswith("add task") or message.lower().startswith("add a task"):
                rough_title = message.split(":", maxsplit=1)[-1].strip() if ":" in message else message
                payload = TaskCreate(title=rough_title or "New Task")
                created = self.tasks.create_task(user_id, payload)
                return FlowMessageResponse(
                    response=f"Added task '{created.title}' as {created.priority}. Want me to schedule time for it today?"
                )

            pending = self.tasks.list_tasks(user_id, status="pending")
            if not pending:
                return FlowMessageResponse(response="You have no pending tasks right now.")
            items = "; ".join([f"{t.title} ({t.priority})" for t in pending[:5]])
            return FlowMessageResponse(response=f"Your pending tasks: {items}.")

        if intent == "optimize":
            plan = self.optimizer.optimize_today(user_id)
            suggestions = plan["suggestions"]
            if not suggestions:
                return FlowMessageResponse(response="I could not find good slots from your current free windows today.")

            lines = []
            action_payload = {"items": []}
            for s in suggestions[:6]:
                lines.append(f"{self._fmt(s['start'])} - {s['title']} ({s['duration']} min) ★")
                action_payload["items"].append(
                    {
                        "summary": s["title"],
                        "start": s["start"].isoformat(),
                        "end": s["end"].isoformat(),
                        "taskId": s["taskId"],
                    }
                )

            msg = "Here is your optimized schedule for today:\n" + "\n".join(lines) + "\nShall I add this to your calendar?"
            return FlowMessageResponse(
                response=msg,
                requires_confirmation=True,
                proposed_action=ProposedAction(action_type="calendar.create_event", payload=action_payload),
            )

        if intent == "schedule":
            proposal = self.scheduler.propose_slot(user_id, message)
            if not proposal.get("can_schedule"):
                return FlowMessageResponse(response=proposal["message"])

            return FlowMessageResponse(
                response=proposal["message"],
                requires_confirmation=True,
                proposed_action=ProposedAction(
                    action_type="calendar.create_event",
                    payload={
                        "items": [
                            {
                                "summary": proposal["summary"],
                                "start": proposal["start"].isoformat(),
                                "end": proposal["end"].isoformat(),
                            }
                        ]
                    },
                ),
            )

        return FlowMessageResponse(
            response="I can help with free slots, tasks, and scheduling. Tell me what you want to plan next."
        )

    def confirm_action(self, user_id: str, action_type: str, payload: dict) -> str:
        if action_type == "calendar.create_event":
            items = payload.get("items", [])
            if not items:
                return "Nothing to add."

            created_count = 0
            for item in items:
                event = self.calendar.create_event(
                    user_id=user_id,
                    summary=item["summary"],
                    start=datetime.fromisoformat(item["start"]),
                    end=datetime.fromisoformat(item["end"]),
                    description="Created by FlowAgent",
                )
                created_count += 1
                task_id = item.get("taskId")
                if task_id:
                    self.tasks.update_task(
                        user_id,
                        task_id,
                        TaskUpdate(calendar_event_id=event.get("id")),
                    )

            return f"Done. Added {created_count} event(s) to your calendar."

        if action_type == "task.create":
            task_payload = payload.get("task")
            if not task_payload:
                return "No task details found."
            created = self.tasks.create_task(user_id, TaskCreate(**task_payload))
            return f"Done. Added task '{created.title}'."

        return "No action was executed."
