from datetime import datetime
from pathlib import Path
import json


ACTION_LOG = Path(
    "storage/action_log.jsonl"
)


def prepare_escalation(
    ticket_id,
    reason,
    priority,
    user_context
):

    action = {

        "type": "create_escalation",

        "ticket_id": ticket_id,

        "reason": reason,

        "priority": priority

    }

    return json.dumps({

        "status": "confirmation_required",

        "action": action,

        "message":
            "Escalation prepared. "
            "Explicit user confirmation is required."

    })


def execute_escalation(
    action,
    user_context
):

    ACTION_LOG.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    record = {

        **action,

        "executed_at":
            datetime.utcnow().isoformat() + "Z",

        "executed_by_role":
            user_context["role"],

        "account_scope":
            user_context["account_scope"]

    }

    with ACTION_LOG.open(
        "a",
        encoding="utf-8"
    ) as file:

        file.write(
            json.dumps(record) + "\n"
        )

    return (
        f"Escalation for ticket "
        f"{action['ticket_id']} was created successfully."
    )