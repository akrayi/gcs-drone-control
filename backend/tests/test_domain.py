from itertools import permutations
from types import SimpleNamespace
from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.domain import Command, transition


def drone(**kwargs):
    return SimpleNamespace(**dict(dict(id=1, version=0, mode="GROUNDED", x=0, y=0,
                                      altitude=0, safety_latched=False), **kwargs))


def command(action, version=0, **kwargs):
    return Command(request_id=uuid4(), action=action, expected_version=version, **kwargs)


@pytest.mark.parametrize("actions", list(permutations(["TAKEOFF", "RETURN_HOME"])))
def test_return_home_wins_both_orderings(actions):
    d = drone()
    for action in actions:
        transition(d, command(action))
    assert (d.mode, d.altitude, d.safety_latched) == ("GROUNDED", 0, True)
    assert transition(d, command("TAKEOFF", d.version)) == "SAFETY_LATCHED"


def test_grounded_return_home_never_moves_or_launches():
    d = drone(x=32, y=-19)
    assert transition(d, command("RETURN_HOME")) is None
    assert (d.x, d.y, d.altitude, d.mode) == (32, -19, 0, "GROUNDED")


def test_airborne_return_goes_home_and_lands():
    d = drone(mode="AIRBORNE", altitude=10, x=42, y=31)
    transition(d, command("RETURN_HOME", 999))
    assert (d.x, d.y, d.altitude, d.mode, d.safety_latched) == (0, 0, 0, "GROUNDED", True)


def test_grounded_move_rejected():
    d = drone()
    assert transition(d, command("MOVE", x=5, y=5)) == "MUST_BE_AIRBORNE"
    assert (d.version, d.x, d.y) == (0, 0, 0)


def test_stale_clear_cannot_remove_new_safety_latch():
    d = drone()
    transition(d, command("RETURN_HOME"))
    assert transition(d, command("CLEAR_SAFETY", 0)) == "STALE_VERSION"
    assert d.safety_latched
    assert transition(d, command("CLEAR_SAFETY", 1)) is None
    assert transition(d, command("TAKEOFF", 2)) is None


@pytest.mark.parametrize("extra", [{"x": float('nan'), "y": 0}, {"x": 101, "y": 0}, {"x": 0, "y": float('inf')}])
def test_invalid_coordinates(extra):
    with pytest.raises(ValidationError):
        command("MOVE", **extra)


def test_non_safety_commands_require_version():
    with pytest.raises(ValidationError):
        Command(request_id=uuid4(), action="TAKEOFF")
