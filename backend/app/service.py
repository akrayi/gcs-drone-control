from sqlalchemy import select
from fastapi import HTTPException
from .db import Session, Drone, CommandLog
from .domain import state, transition
from .security import authenticate, authorize


def execute(token, command):
    with Session.begin() as db:
        user = authenticate(db, token)
        authorize(user, command.action)
        # All API replicas contend on the same row, not on a Python mutex.
        drone = db.scalar(select(Drone).where(Drone.id == 1).with_for_update())
        if drone is None:
            raise HTTPException(503, "Database needs initialization")
        request_id = str(command.request_id)
        payload = command.model_dump(mode="json")
        prior = db.get(CommandLog, request_id)
        if prior:
            if prior.username != user.username or prior.payload != payload:
                raise HTTPException(409, "Idempotency key already used for another request")
            return prior.status_code, prior.response
        reason = transition(drone, command)
        code = 409 if reason else 200
        result = {"accepted": not reason, "reason": reason or "APPLIED",
                  "request_id": request_id, "state": state(drone)}
        db.add(CommandLog(request_id=request_id, username=user.username, action=command.action,
                          payload=payload, response=result, status_code=code))
        # Returning exits the transaction: state and receipt commit together.
        return code, result


def snapshot(token):
    with Session.begin() as db:
        user = authenticate(db, token)
        authorize(user, "READ")
        drone = db.scalar(select(Drone).where(Drone.id == 1).with_for_update(read=True))
        if drone is None:
            raise HTTPException(503, "Database needs initialization")
        logs = db.scalars(select(CommandLog).order_by(CommandLog.created_at.desc(), CommandLog.request_id).limit(20)).all()
        return {"state": state(drone), "user": {"username": user.username, "role": user.role},
                "events": [{"request_id": row.request_id, "username": row.username,
                            "action": row.action, "reason": row.response["reason"],
                            "created_at": row.created_at.isoformat()} for row in logs]}
