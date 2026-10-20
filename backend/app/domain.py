"""Pure simulator transitions. Database transaction owns serialization."""
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

Action = Literal["TAKEOFF", "MOVE", "LAND", "RETURN_HOME", "CLEAR_SAFETY"]


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    request_id: UUID
    action: Action
    expected_version: int | None = Field(default=None, ge=0)
    x: float | None = Field(default=None, ge=-100, le=100)
    y: float | None = Field(default=None, ge=-100, le=100)

    @model_validator(mode="after")
    def valid_command(self):
        if self.action != "RETURN_HOME" and self.expected_version is None:
            raise ValueError("expected_version required except for RETURN_HOME")
        if self.action == "MOVE" and (self.x is None or self.y is None):
            raise ValueError("MOVE requires x and y")
        if self.action != "MOVE" and (self.x is not None or self.y is not None):
            raise ValueError("Only MOVE accepts coordinates")
        return self


def state(drone):
    return {key: getattr(drone, key) for key in
            ("id", "version", "mode", "x", "y", "altitude", "safety_latched")}


def transition(drone, command: Command):
    """Return rejection reason, or mutate a successful transition."""
    action = command.action
    # Safety ignores stale versions. It must win in either row-lock ordering.
    if action == "RETURN_HOME":
        drone.safety_latched = True
        if drone.mode == "AIRBORNE":
            drone.x = drone.y = 0
        # Grounded RETURN_HOME never moves the craft or starts its motors.
        drone.mode, drone.altitude = "GROUNDED", 0
    else:
        if command.expected_version != drone.version:
            return "STALE_VERSION"
        if action == "CLEAR_SAFETY":
            if drone.mode != "GROUNDED":
                return "MUST_BE_GROUNDED"
            drone.safety_latched = False
        elif action == "TAKEOFF":
            if drone.safety_latched:
                return "SAFETY_LATCHED"
            if drone.mode != "GROUNDED":
                return "ALREADY_AIRBORNE"
            drone.mode, drone.altitude = "AIRBORNE", 10
        elif action == "MOVE":
            if drone.safety_latched:
                return "SAFETY_LATCHED"
            if drone.mode != "AIRBORNE":
                return "MUST_BE_AIRBORNE"
            drone.x, drone.y = command.x, command.y
        elif action == "LAND":
            drone.mode, drone.altitude = "GROUNDED", 0
    drone.version += 1
    return None
